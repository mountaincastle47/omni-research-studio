"""Multi-perspective OmniSweep web research agent powered by Google GenAI and Google Search grounding."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional
import concurrent.futures
from urllib.parse import urlparse

from google import genai
import httpx
from google.genai import types

GEMINI_HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=15.0, pool=10.0)

from core.config import DEFAULT_DISCOVERY_MODEL
from core.resilience import (
    TaskCancelledError,
    call_with_exponential_backoff,
    is_rate_limit_error,
    sleep_with_cancel_check,
)
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    err_msg = str(exc).lower()
    return (
        "429" in err_msg
        or "resource_exhausted" in err_msg
        or "quota" in err_msg
        or "readtimeout" in err_msg
        or "connecttimeout" in err_msg
        or isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout))
        or is_rate_limit_error(exc)
    )


@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1.0, min=2.0, max=30.0),
    retry=retry_if_exception(_is_retryable_gemini_error),
    reraise=True,
)
def _generate_content_with_retry(
    client: genai.Client,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    heartbeat_callback: Optional[Callable[[str], None]] = None,
) -> types.GenerateContentResponse:
    """Execute generate_content with tenacity exponential jitter retry against HTTP 429 and resource exhaustion."""
    if heartbeat_callback:
        heartbeat_callback("omnisweep_phase_2")
    res = client.models.generate_content(model=model, contents=contents, config=config)
    if heartbeat_callback:
        heartbeat_callback("omnisweep_phase_2")
    return res


STRICT_FORMATTING_RULE = (
    "STRICT FORMATTING RULE: Absolutely NO ASCII diagrams, box drawings (e.g. +---+ or |), or text art. "
    "Never draw tables using hyphens, pipes, or spaces unless constructing a fully populated standard Markdown table. "
    "Never output empty tables, blank table rows, or orphaned bullet points. "
    "Express all system pipelines, trade-offs, and failure trajectories purely as standard hierarchical bullet points with bold lead-ins."
)

QUERY_FORMULATION_DIRECTIVE = (
    "QUERY FORMULATION & MULTI-LINGUAL GROUNDING DIRECTIVE:\n"
    "You are an elite research intelligence agent tasked with generating high-yield, native search queries for Google Search Grounding. "
    "You must decouple the user's input prompt language from the search query languages.\n\n"
    "Evaluate every research topic across four mandatory dimensions before outputting queries:\n\n"
    "1. Primary Source & Information-Density Origin:\n"
    "   - Identify where the deepest, un-sanitized, primary technical or cultural documentation originates globally.\n"
    "   - If primary documentation, telemetry, declassified records, or specialized dev/community archives exist natively in a specific language, "
    "formulate queries directly in that NATIVE language using official nomenclature:\n"
    "     * Islamic jurisprudence, theology, or Arab history -> Classical & modern Arabic terms (alongside English comparative scholarship).\n"
    "     * Soviet/Russian military engineering, ballistic trials, aerospace prototypes -> Russian technical designations "
    "(Cyrillic: e.g., 'Объект 477 Молот автомат заряжания', 'Су-47 Беркут крыло обратной стреловидности').\n"
    "     * Japanese gaming mechanics, anime production, aerospace/industrial dev -> Japanese terms "
    "(Kanji/Katakana: e.g., developer postmortems, Famitsu/technical interviews).\n"
    "     * Western scientific consensus, software engineering, defense whitepapers -> English.\n"
    "     * South Korean domestic policy, ROK defense procurement (DAPA/ADD), local law, or domestic culture -> Korean.\n\n"
    "2. Cultural & Geopolitical Narrative Divergence:\n"
    "   - Determine if the subject entails conflicting historical, theological, or geopolitical perspectives across cultural spheres "
    "(e.g., Western academic/security framing vs. Middle Eastern theological/societal framing; East Asian regional historical assessments vs. Western consensus).\n"
    "   - When cultural divergence exists, generate orthogonal query sets across BOTH spheres:\n"
    "     * Issue native-language queries to capture the internal/primary cultural perspective.\n"
    "     * Issue English/global queries to capture international comparative, critical, or methodological analyses.\n"
    "     * Issue queries in the user's prompt language to capture local context and terminology.\n\n"
    "3. Search Syntax & Density Rules:\n"
    "   - Output concise, keyword-dense search queries (3 to 6 words each).\n"
    "   - Eliminate conversational filler, punctuation, and full sentences.\n"
    "   - Use exact industry terms, military designations, scriptural concepts, or legal codes rather than translated approximations.\n\n"
    "4. Dynamic Incentive & Paradigm Divergence:\n"
    "   - Epistemic Evaluation:\n"
    "     Assess whether the core subject involves competing normative frameworks, fundamentally opposing incentive structures, or un-reconciled structural trade-offs "
    "(e.g., centralized control vs. decentralized autonomy; market-clearing mechanisms vs. command allocation; permissive vs. restrictive licensing; safety-first precaution vs. accelerationism).\n"
    "   - Conditional Branching:\n"
    "     * If CONTESTED / PARADIGM-SPLIT:\n"
    "       Autonomously identify the 2–3 major competing schools of thought or institutional frameworks governing the topic. "
    "Formulate balanced, orthogonal query sets that investigate the empirical arguments, measurable trade-offs, and failure points of EACH competing paradigm.\n"
    "     * If PURELY PHYSICAL / MECHANICAL / EMPIRICAL:\n"
    "       (e.g., aerodynamic shear limits, ballistic penetration, circuit design, bug reproduction, baseline game engine physics):\n"
    "       Do NOT fabricate political or philosophical angles. Focus queries strictly on physical failure thresholds, telemetry, material boundaries, and empirical test data.\n"
    "   - Query Neutrality:\n"
    "     * Frame all queries in technical, objective, and outcome-oriented language "
    "(measuring efficiency, latency, deadweight loss, failure rates, total cost of ownership, adoption friction).\n"
    "     * Strictly forbid partisan slogans, polemics, or moralizing editorial search terms."
)

OUTPUT_LANGUAGE_CONSTRAINT = (
    "OUTPUT LANGUAGE CONSTRAINT:\n"
    "- Regardless of the languages of the ingested source snippets (e.g., Russian, Arabic, Japanese, Korean), "
    "NEVER output the synthesized report in a mix of those source languages.\n"
    "- Always synthesize the canonical perspective report and grounded synthesis in clear, rigorous academic ENGLISH "
    "(to serve as the canonical 'Original / 원문' baseline).\n"
    "- Maintain all technical designations and official names in their authoritative script with English transliterations where appropriate."
)


_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_JAPANESE_KANA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")
_HANGUL_RE = re.compile(r"[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]")
_CJK_HAN_RE = re.compile(r"[\u4E00-\u9FFF]")

_THEOLOGICAL_AR_KEYWORDS = (
    "فقه",
    "شريعة",
    "مقاصد",
    "إسلام",
    "حديث",
    "قرآن",
    "فتوى",
    "أصول",
    "fiqh",
    "sharia",
    "maqasid",
    "usul",
    "hadith",
    "tafseer",
    "tafsir",
    "islamic jurisprudence",
    "theology",
)


def detect_linguistic_origin_tag(
    text: str,
    uri: str = "",
    perspective_name: str = "",
) -> str:
    """Classify the linguistic and cultural origin of a discovered source or snippet."""
    combined = f"{text or ''} {uri or ''}"
    lower_combined = combined.lower()
    lower_persp = (perspective_name or "").lower()

    domain = ""
    if uri and uri.startswith("http"):
        try:
            domain = (urlparse(uri).netloc or "").lower()
        except Exception:
            domain = ""

    if _ARABIC_RE.search(combined) or domain.endswith((".sa", ".eg", ".ae", ".qa", ".jo", ".ma")):
        if any(k in lower_combined for k in _THEOLOGICAL_AR_KEYWORDS) or "historical" in lower_persp or "comparative" in lower_persp:
            return "AR/Theological"
        return "AR/Primary"

    if _CYRILLIC_RE.search(combined) or domain.endswith((".ru", ".su", ".by", ".ua", ".рф")):
        return "RU/Primary"

    if _JAPANESE_KANA_RE.search(combined) or domain.endswith(".jp"):
        return "JA/Primary"

    if _HANGUL_RE.search(combined) or domain.endswith(".kr"):
        return "KO/Primary"

    if _CJK_HAN_RE.search(combined) or domain.endswith((".cn", ".tw", ".hk")):
        return "ZH/Primary"

    if any(k in lower_combined for k in ("fiqh", "maqasid", "sharia", "islamic jurisprudence")):
        return "EN/Comparative"

    if "historical" in lower_persp or "comparative" in lower_persp or "skeptic" in lower_persp:
        return "EN/Comparative"

    return "EN/Primary"


def classify_source_authority(uri: str, title: str = "", content: str = "") -> str:
    """Classify source authority into PRIMARY/EMPIRICAL, SECONDARY/SCHOLARLY, or TERTIARY/COMMENTARY."""
    lower_uri = (uri or "").lower()
    lower_title = (title or "").lower()
    combined = f"{lower_uri} {lower_title} {content[:500].lower()}"

    # 1. Primary / Empirical: Government, military, statutes, patents, court archives, telemetry logs
    primary_tlds = (".gov", ".mil", ".go.kr", ".gov.uk", ".europa.eu", ".gouv.fr", ".admin.ch", ".bund.de")
    if any(lower_uri.endswith(tld) or f"{tld}/" in lower_uri for tld in primary_tlds):
        return "PRIMARY/EMPIRICAL"
    if any(domain in lower_uri for domain in ("patents.google.com", "uspto.gov", "epo.org", "wipo.int", "sec.gov", "fara.gov", "supremecourt.gov")):
        return "PRIMARY/EMPIRICAL"
    if any(k in combined for k in ("telemetry log", "flight recorder", "blackbox data", "declassified document", "statutory code", "official gazette", "test bench data", "sensor readout")):
        return "PRIMARY/EMPIRICAL"

    # 2. Secondary / Scholarly: Academic portals, preprints, peer-reviewed journals, defense analysis institutes
    scholarly_tlds = (".edu", ".ac.kr", ".ac.uk", ".edu.au", ".edu.cn")
    if any(lower_uri.endswith(tld) or f"{tld}/" in lower_uri for tld in scholarly_tlds):
        return "SECONDARY/SCHOLARLY"
    scholarly_domains = (
        "arxiv.org", "biorxiv.org", "medrxiv.org", "ieee.org", "jstor.org", "nature.com",
        "science.org", "springer.com", "sciencedirect.com", "wiley.com", "cell.com",
        "pnas.org", "nih.gov", "ncbi.nlm.nih.gov", "thelancet.com", "rusi.org", "janes.com",
        "csis.org", "iiss.org", "rand.org", "sipri.org", "acm.org"
    )
    if any(domain in lower_uri for domain in scholarly_domains):
        return "SECONDARY/SCHOLARLY"
    if any(k in combined for k in ("peer-reviewed", "journal article", "whitepaper", "technical report", "meta-analysis", "systematic review", "monograph")):
        return "SECONDARY/SCHOLARLY"

    # 3. Tertiary / Commentary: News outlets, tech blogs, commentary forums
    return "TERTIARY/COMMENTARY"


def format_multilingual_source_tag(
    perspective_name: str,
    origin_tag: str,
    title: str,
    authority_tag: str = "",
) -> str:
    """Format an ingested source title with perspective, origin, and authority tier tags."""
    clean_title = (title or "Untitled Source").strip()
    clean_persp = (perspective_name or "OmniSweep").strip()
    clean_origin = (origin_tag or "EN/Primary").strip()
    auth_part = f" [{authority_tag.strip()}]" if authority_tag else ""
    prefix = f"[WEB SWEEP] [{clean_persp}] [{clean_origin}]{auth_part}"
    if clean_title.startswith("[WEB SWEEP]"):
        return clean_title
    return f"{prefix} {clean_title}"


@dataclass
class GroundingReference:
    """Represents a verified web grounding URI returned by Google Search grounding."""

    title: str
    uri: str
    perspective_name: str
    snippet: str = ""
    origin_tag: str = ""
    authority_tier: str = ""

    def __post_init__(self) -> None:
        if not self.origin_tag:
            self.origin_tag = detect_linguistic_origin_tag(
                f"{self.title} {self.snippet}",
                uri=self.uri,
                perspective_name=self.perspective_name,
            )
        if not self.authority_tier:
            self.authority_tier = classify_source_authority(
                uri=self.uri,
                title=f"{self.title} {self.snippet}",
            )

    @property
    def tagged_title(self) -> str:
        """Return `[WEB SWEEP] [<Perspective>] [<Lang/Origin>] [<Authority>] <Title>`."""
        return format_multilingual_source_tag(
            self.perspective_name, self.origin_tag, self.title, self.authority_tier
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GroundingReference:
        return cls(
            title=str(data.get("title", "")),
            uri=str(data.get("uri", "")),
            perspective_name=str(data.get("perspective_name", "")),
            snippet=str(data.get("snippet", "")),
            origin_tag=str(data.get("origin_tag", "")),
        )


@dataclass
class ScrapedSource:
    """A Tier-2 deep-scrape outcome: full article text, or the retained Google grounding snippet on failure."""

    title: str
    uri: str
    perspective_name: str
    text: str
    full_text: bool
    origin_tag: str = ""

    @property
    def tagged_title(self) -> str:
        """`[WEB FULL-TEXT] [{Perspective}] {Page Title}` or `[WEB SNIPPET] [{Perspective}] {Page Title}`."""
        kind = "WEB FULL-TEXT" if self.full_text else "WEB SNIPPET"
        return f"[{kind}] [{self.perspective_name}] {self.title}".strip()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScrapedSource:
        return cls(
            title=str(data.get("title", "")),
            uri=str(data.get("uri", "")),
            perspective_name=str(data.get("perspective_name", "")),
            text=str(data.get("text", "")),
            full_text=bool(data.get("full_text", False)),
            origin_tag=str(data.get("origin_tag", "")),
        )


@dataclass
class PerspectiveReport:
    """Contains the research questions, grounded analysis, and web URIs for a single expert persona."""

    perspective_id: str
    perspective_name: str
    perspective_role: str
    sub_queries: List[str]
    analysis_markdown: str
    grounding_references: List[GroundingReference] = field(default_factory=list)
    search_queries_executed: List[str] = field(default_factory=list)
    scraped_sources: List[ScrapedSource] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "perspective_id": self.perspective_id,
            "perspective_name": self.perspective_name,
            "perspective_role": self.perspective_role,
            "sub_queries": list(self.sub_queries),
            "analysis_markdown": self.analysis_markdown,
            "grounding_references": [r.to_dict() for r in self.grounding_references],
            "search_queries_executed": list(self.search_queries_executed),
            "scraped_sources": [s.to_dict() for s in self.scraped_sources],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PerspectiveReport:
        return cls(
            perspective_id=str(data.get("perspective_id", "")),
            perspective_name=str(data.get("perspective_name", "")),
            perspective_role=str(data.get("perspective_role", "")),
            sub_queries=[str(q) for q in data.get("sub_queries", [])],
            analysis_markdown=str(data.get("analysis_markdown", "")),
            grounding_references=[
                GroundingReference.from_dict(r) for r in data.get("grounding_references", [])
            ],
            search_queries_executed=[str(q) for q in data.get("search_queries_executed", [])],
            scraped_sources=[ScrapedSource.from_dict(s) for s in data.get("scraped_sources", [])],
        )


_LOW_AUTHORITY_DOMAINS = (
    "youtube.", "youtu.be", "facebook.", "twitter.", "x.com", "instagram.", "tiktok.", "pinterest.",
    "reddit.", "quora.", "linkedin.", "t.me", "naver.me", "blog.naver", "tistory.", "medium.com",
)
_HIGH_AUTHORITY_HINTS = (
    "wikipedia.org", "arxiv.org", "nature.com", "science.org", "sciencedirect.com", "springer.com",
    "ieee.org", "acm.org", "nih.gov", "who.int", "oecd.org", "iea.org", "worldbank.org", "un.org",
    "reuters.com", "apnews.com", "bbc.", "nytimes.com", "ft.com", "economist.com", "britannica.com",
    "github.com", "mozilla.org", "w3.org", "ietf.org", "nasa.gov", "nrel.gov", "energy.gov",
    "kaeri.re.kr", "krei.re.kr", "go.kr", "kostat.go.kr", "ac.kr", "jstor.org", "oup.com", "cambridge.org",
)
_HIGH_AUTHORITY_TLD_SUFFIXES = (".gov", ".edu", ".mil", ".int", ".ac.uk", ".gov.uk", ".go.kr", ".ac.kr", ".or.kr", ".re.kr", ".go.jp", ".ac.jp")
_DOMAIN_LIKE_RE = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", re.IGNORECASE)


def _reference_domain(ref: GroundingReference) -> str:
    """Google grounding URIs are opaque redirects, so the chunk title (usually the site domain) is the real domain."""
    title = (ref.title or "").strip().lower()
    if _DOMAIN_LIKE_RE.match(title):
        return title.removeprefix("www.")
    try:
        host = (urlparse(ref.uri).netloc or "").lower().removeprefix("www.")
    except Exception:
        host = ""
    if host and "vertexaisearch.cloud.google.com" not in host:
        return host
    return title


def _authority_score(ref: GroundingReference) -> int:
    domain = _reference_domain(ref)
    if not domain:
        return 0
    if any(marker in domain for marker in _LOW_AUTHORITY_DOMAINS):
        return -5
    score = 1
    if any(hint in domain for hint in _HIGH_AUTHORITY_HINTS):
        score += 4
    if domain.endswith(_HIGH_AUTHORITY_TLD_SUFFIXES) or domain.endswith(".org"):
        score += 3
    if domain.endswith((".com", ".net", ".io")):
        score += 1
    return score


def select_authoritative_references(
    references: List[GroundingReference],
    limit: int = 2,
) -> List[GroundingReference]:
    """Pick the top `limit` unique HTTP/HTTPS references, preferring authoritative and distinct domains."""
    candidates: List[GroundingReference] = []
    seen_uris: set[str] = set()
    for ref in references:
        uri = (ref.uri or "").strip()
        if not uri.lower().startswith(("http://", "https://")) or uri in seen_uris:
            continue
        seen_uris.add(uri)
        candidates.append(ref)

    ranked = sorted(enumerate(candidates), key=lambda pair: (-_authority_score(pair[1]), pair[0]))
    selected: List[GroundingReference] = []
    used_domains: set[str] = set()
    for _, ref in ranked:
        if _authority_score(ref) < 0:
            continue
        domain = _reference_domain(ref)
        if domain and domain in used_domains:
            continue
        used_domains.add(domain)
        selected.append(ref)
        if len(selected) >= limit:
            break
    return selected



@dataclass
class OmniSweepDiscoveryResult:
    """Aggregated output of a multi-perspective OmniSweep research session."""

    topic: str
    model_used: str
    perspective_reports: List[PerspectiveReport] = field(default_factory=list)
    all_grounding_references: List[GroundingReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "model_used": self.model_used,
            "perspective_reports": [p.to_dict() for p in self.perspective_reports],
            "all_grounding_references": [r.to_dict() for r in self.all_grounding_references],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OmniSweepDiscoveryResult:
        return cls(
            topic=str(data.get("topic", "")),
            model_used=str(data.get("model_used", DEFAULT_DISCOVERY_MODEL)),
            perspective_reports=[
                PerspectiveReport.from_dict(p) for p in data.get("perspective_reports", [])
            ],
            all_grounding_references=[
                GroundingReference.from_dict(r) for r in data.get("all_grounding_references", [])
            ],
        )


class OmniSweepDiscoveryAgent:
    """Executes OmniSweep multi-perspective retrieval and question-driven web discovery."""

    def __init__(
        self,
        client: genai.Client,
        model_name: str = DEFAULT_DISCOVERY_MODEL,
        inter_perspective_delay: float = 2.5,
        deep_scrape: bool = True,
        article_fetcher: Optional[Callable[[str, int], Optional[Any]]] = None,
        scrape_status_text: str = "Deep-scraping full text from authoritative sources...",
        max_scrape_per_perspective: int = 2,
        scrape_timeout: int = 6,
    ) -> None:
        self.client = client
        self.model_name = model_name
        self.inter_perspective_delay = inter_perspective_delay
        self.deep_scrape = deep_scrape
        self.scrape_status_text = scrape_status_text
        self.max_scrape_per_perspective = max_scrape_per_perspective
        self.scrape_timeout = scrape_timeout
        if article_fetcher is None:
            from core.web_scraper import fetch_web_article

            article_fetcher = fetch_web_article
        self.article_fetcher = article_fetcher

    def scrape_perspective_sources(
        self,
        report: PerspectiveReport,
        progress_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        heartbeat_callback: Optional[Callable[[str], None]] = None,
    ) -> List[ScrapedSource]:
        """Fetch full text for top authoritative grounding links with concurrent futures, per-future timeouts, and heartbeat updates."""
        targets = select_authoritative_references(
            report.grounding_references, limit=self.max_scrape_per_perspective
        )
        if not targets:
            return []

        def _fetch_single(ref: Any) -> ScrapedSource:
            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")
            article = None
            try:
                article = self.article_fetcher(ref.uri, self.scrape_timeout)
            except Exception:
                article = None

            if article is not None and getattr(article, "text", "").strip():
                page_title = (getattr(article, "title", "") or ref.title or ref.uri).strip()
                text = str(article.text)
                full_text = True
                final_uri = str(getattr(article, "url", "") or ref.uri)
            else:
                page_title = (ref.title or ref.uri).strip()
                text = ref.snippet or f"Discovered via {report.perspective_name} grounding search."
                full_text = False
                final_uri = ref.uri

            return ScrapedSource(
                title=page_title,
                uri=final_uri,
                perspective_name=report.perspective_name,
                text=text,
                full_text=full_text,
                origin_tag=detect_linguistic_origin_tag(
                    f"{page_title} {text[:600]}",
                    uri=final_uri,
                    perspective_name=report.perspective_name,
                ),
            )

        results: List[ScrapedSource] = []
        max_workers = min(len(targets), 3)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ref = {executor.submit(_fetch_single, ref): ref for ref in targets}
            for future in concurrent.futures.as_completed(future_to_ref, timeout=self.scrape_timeout * 2.5):
                if cancel_check and cancel_check():
                    raise TaskCancelledError("Task aborted by user.")
                try:
                    res = future.result(timeout=1.0)
                    results.append(res)
                except Exception:
                    ref = future_to_ref[future]
                    results.append(
                        ScrapedSource(
                            title=ref.title or ref.uri,
                            uri=ref.uri,
                            perspective_name=report.perspective_name,
                            text=ref.snippet or "Grounding snippet fallback.",
                            full_text=False,
                            origin_tag=detect_linguistic_origin_tag(
                                f"{ref.title} {ref.snippet[:600]}",
                                uri=ref.uri,
                                perspective_name=report.perspective_name,
                            ),
                        )
                    )
                if heartbeat_callback:
                    heartbeat_callback("omnisweep_phase_2")
                if progress_callback:
                    progress_callback(
                        f"[{report.perspective_name}] {self.scrape_status_text} ({len(results)}/{len(targets)})"
                    )

        return results

    def run_discovery(
        self,
        topic: str,
        perspectives: List[Dict[str, str]],
        corpus_summary: str = "",
        progress_callback: Optional[Callable[[str], None]] = None,
        step_progress_callback: Optional[Callable[[int, int, str, int], None]] = None,
        subphase_callback: Optional[Callable[[int, int, str, float], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        heartbeat_callback: Optional[Callable[[str], None]] = None,
    ) -> OmniSweepDiscoveryResult:
        """Run multi-perspective grounded web discovery with 3 sub-phases per perspective and ETA tracking."""
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("Research topic cannot be empty.")

        if not perspectives:
            raise ValueError("At least one research perspective must be selected.")

        result = OmniSweepDiscoveryResult(topic=cleaned_topic, model_used=self.model_name)
        seen_uris: set[str] = set()

        total = len(perspectives)
        completed_durations: List[float] = []

        for index, persona in enumerate(perspectives, start=1):
            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")

            if index > 1 and self.inter_perspective_delay > 0:
                pacing_msg = f"Pacing API calls to respect rate limits... ({self.inter_perspective_delay:.0f}s)"
                if progress_callback:
                    progress_callback(pacing_msg)
                sleep_with_cancel_check(self.inter_perspective_delay, cancel_check=cancel_check)

            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")

            step_start = time.monotonic()
            p_id = persona.get("id", f"persona_{index}")
            p_name = persona.get("name", f"Expert Perspective {index}")
            p_role = persona.get("role", "Domain specialist conducting deep investigative research.")

            avg_dur = (
                sum(completed_durations) / len(completed_durations)
                if completed_durations
                else 9.0
            )
            remaining_perspectives = total - index + 1
            remaining_pacing = max(0, total - index) * self.inter_perspective_delay
            eta_seconds = max(2, int(round(remaining_perspectives * avg_dur + remaining_pacing)))

            # Sub-phase 1: Query formulation (15% of perspective slice)
            if subphase_callback:
                subphase_callback(index, total, f"[{index}/{total}] {p_name} — (1/3) Query formulation...", 0.15)

            base_pct = int(((index - 1) / total) * 100)
            status_msg = f"[{index}/{total}] {p_name} — formulating cross-lingual search queries..."
            if progress_callback:
                progress_callback(status_msg)
            if step_progress_callback:
                step_progress_callback(base_pct + int(15 / total), eta_seconds, status_msg, index)

            formulated_queries = call_with_exponential_backoff(
                self.formulate_search_queries,
                topic=cleaned_topic,
                perspective_name=p_name,
                perspective_role=p_role,
                corpus_summary=corpus_summary,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")

            # Sub-phase 2: Search grounding (60% of perspective slice -> 75% cumulative within slice)
            if subphase_callback:
                subphase_callback(index, total, f"[{index}/{total}] {p_name} — (2/3) Google Search grounding...", 0.75)
            if heartbeat_callback:
                heartbeat_callback("omnisweep_phase_2")

            try:
                report = call_with_exponential_backoff(
                    self._investigate_perspective,
                    topic=cleaned_topic,
                    perspective_id=p_id,
                    perspective_name=p_name,
                    perspective_role=p_role,
                    corpus_summary=corpus_summary,
                    formulated_queries=formulated_queries,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                    heartbeat_callback=heartbeat_callback,
                )

                if cancel_check and cancel_check():
                    raise TaskCancelledError("Task aborted by user.")

                if heartbeat_callback:
                    heartbeat_callback("omnisweep_phase_2")

                # Tier-2: deep full-text ingestion of the top authoritative links (between cancellation checks)
                if self.deep_scrape and report.grounding_references:
                    report.scraped_sources = self.scrape_perspective_sources(
                        report,
                        progress_callback=progress_callback,
                        cancel_check=cancel_check,
                        heartbeat_callback=heartbeat_callback,
                    )
            except Exception as e:
                if heartbeat_callback:
                    heartbeat_callback("omnisweep_phase_2")
                raise

            # Sub-phase 3: Perspective synthesis (25% of perspective slice -> 100% cumulative within slice)
            if subphase_callback:
                subphase_callback(index, total, f"[{index}/{total}] {p_name} — (3/3) Perspective synthesis...", 1.0)

            result.perspective_reports.append(report)

            for ref in report.grounding_references:
                if ref.uri and ref.uri not in seen_uris:
                    seen_uris.add(ref.uri)
                    result.all_grounding_references.append(ref)

            step_duration = max(0.5, time.monotonic() - step_start)
            completed_durations.append(step_duration)

            done_pct = int((index / total) * 100)
            rem_count = total - index
            avg_now = sum(completed_durations) / len(completed_durations)
            rem_eta = (
                int(round(rem_count * avg_now + max(0, rem_count - 1) * self.inter_perspective_delay))
                if rem_count > 0
                else 0
            )
            if step_progress_callback:
                step_progress_callback(done_pct, rem_eta, f"[{index}/{total}] Completed: {p_name}", index)

        if progress_callback:
            progress_callback(
                f"OmniSweep Discovery complete: {len(result.perspective_reports)} perspectives synthesized, "
                f"{len(result.all_grounding_references)} unique grounded web URIs extracted."
            )

        return result

    def formulate_search_queries(
        self,
        topic: str,
        perspective_name: str = "Systems & Technical Architect",
        perspective_role: str = "Evaluates underlying mechanisms, primary documentation, and structural trade-offs.",
        corpus_summary: str = "",
    ) -> List[str]:
        """Formulate cross-lingual, primary-origin, and culturally divergent Google Search queries."""
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            return []

        context_clause = ""
        if corpus_summary.strip():
            context_clause = f"\nExisting Local Corpus Context:\n{corpus_summary.strip()}\n"

        prompt = (
            f"Assigned Persona: {perspective_name}\n"
            f"Mandate & Analytical Lens: {perspective_role}\n\n"
            f"Research Topic / User Prompt:\n\"{cleaned_topic}\"\n"
            f"{context_clause}\n"
            "Generate 4 to 6 high-yield, keyword-dense Google Search queries (3 to 6 words each) strictly adhering to all four dimensions of the "
            "QUERY FORMULATION & MULTI-LINGUAL GROUNDING DIRECTIVE:\n"
            "1. Primary Source & Information-Density Origin (decouple input language from query language; use native scripts/nomenclature where primary archives originate).\n"
            "2. Cultural & Geopolitical Narrative Divergence (issue orthogonal native and international comparative queries when cultural divergence exists).\n"
            "3. Search Syntax & Density Rules (3 to 6 words, exact technical/legal/domain terms, zero conversational filler).\n"
            "4. Dynamic Incentive & Paradigm Divergence:\n"
            "   - If CONTESTED / PARADIGM-SPLIT: autonomously identify the competing schools/incentive frameworks and formulate balanced, orthogonal queries measuring empirical trade-offs, failure modes, and costs of EACH paradigm.\n"
            "   - If PURELY PHYSICAL / MECHANICAL / EMPIRICAL: do NOT fabricate political, normative, or philosophical angles; focus strictly on physical failure thresholds, telemetry, material boundaries, and empirical test data.\n"
            "   - Frame all queries in objective, outcome-oriented technical language without partisan slogans or editorializing.\n"
            "Output ONLY the raw search queries, one query per line, with no numbering, no bullet points, and no surrounding commentary."
        )

        config = types.GenerateContentConfig(
            system_instruction=QUERY_FORMULATION_DIRECTIVE,
            temperature=0.2,
            http_options=types.HttpOptions(
                timeout=180.0,
                httpx_client=httpx.Client(timeout=GEMINI_HTTPX_TIMEOUT),
            ),
        )

        response = _generate_content_with_retry(
            client=self.client,
            model=self.model_name,
            contents=prompt,
            config=config,
        )

        raw_text = (response.text or "").strip()
        queries: List[str] = []
        for line in raw_text.splitlines():
            cleaned_line = re.sub(r"^[\-\*\•\d\.\)\s\"'`]+", "", line.strip()).strip("\"'` ")
            if cleaned_line and len(cleaned_line) >= 2 and cleaned_line not in queries:
                queries.append(cleaned_line)
        return queries[:8]

    def _investigate_perspective(
        self,
        topic: str,
        perspective_id: str,
        perspective_name: str,
        perspective_role: str,
        corpus_summary: str,
        formulated_queries: Optional[List[str]] = None,
        heartbeat_callback: Optional[Callable[[str], None]] = None,
    ) -> PerspectiveReport:
        """Execute grounded search and analysis for a single expert viewpoint."""
        if formulated_queries is None:
            formulated_queries = self.formulate_search_queries(
                topic=topic,
                perspective_name=perspective_name,
                perspective_role=perspective_role,
                corpus_summary=corpus_summary,
            )

        context_clause = ""
        if corpus_summary.strip():
            context_clause = (
                f"\nExisting Local Corpus Context:\n{corpus_summary.strip()}\n"
                "Identify gaps in the local corpus and verify claims against live web evidence.\n"
            )

        queries_block = ""
        if formulated_queries:
            formatted_q = "\n".join(f"- {q}" for q in formulated_queries)
            queries_block = (
                f"\nCross-Lingual & Multi-Perspective Search Queries to Execute & Ground Against:\n"
                f"{formatted_q}\n"
            )

        system_instruction = (
            "You are a specialized research investigator in an OmniSweep multi-perspective discovery pipeline.\n\n"
            f"{QUERY_FORMULATION_DIRECTIVE}\n\n"
            f"{OUTPUT_LANGUAGE_CONSTRAINT}\n\n"
            f"{STRICT_FORMATTING_RULE}"
        )

        prompt = (
            f"Assigned Persona: {perspective_name}\n"
            f"Mandate & Analytical Lens: {perspective_role}\n\n"
            f"Primary Research Topic / Question:\n\"{topic}\"\n"
            f"{context_clause}"
            f"{queries_block}\n"
            f"{OUTPUT_LANGUAGE_CONSTRAINT}\n\n"
            f"{STRICT_FORMATTING_RULE}\n\n"
            "Execute the following steps rigorously using Google Search grounding:\n"
            "1. Formulate 3 specific, high-leverage investigative questions that only someone with your analytical lens would ask.\n"
            "2. Conduct a comprehensive, evidence-dense analysis answering those questions with concrete metrics, dates, mechanisms, and technical/cultural facts grounded in both primary native-language sources and international comparative scholarship.\n"
            "3. Explicitly highlight points of contention, cultural/geopolitical narrative divergence, limitations, or empirical trade-offs.\n\n"
            "Format your output in clean English Markdown with the following sections:\n"
            "### Investigative Questions\n"
            "- Bullet list of the 3 targeted questions.\n\n"
            "### Grounded Technical Findings\n"
            "Detailed, multi-paragraph analysis and hierarchical bullet points with bold lead-ins backed by live search facts.\n\n"
            "### Critical Bottlenecks & Open Risks\n"
            "Key counter-arguments, edge cases, or unresolved constraints."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            http_options=types.HttpOptions(
                timeout=180.0,
                httpx_client=httpx.Client(timeout=GEMINI_HTTPX_TIMEOUT),
            ),
        )

        response = _generate_content_with_retry(
            client=self.client,
            model=self.model_name,
            contents=prompt,
            config=config,
            heartbeat_callback=heartbeat_callback,
        )

        analysis_text = (response.text or "").strip()
        if not analysis_text:
            analysis_text = f"No text returned for perspective {perspective_name}."

        sub_queries = self._extract_questions_from_markdown(analysis_text)
        grounding_refs, search_queries = self._extract_grounding_metadata(
            response,
            perspective_name,
            seed_queries=formulated_queries,
        )

        return PerspectiveReport(
            perspective_id=perspective_id,
            perspective_name=perspective_name,
            perspective_role=perspective_role,
            sub_queries=sub_queries,
            analysis_markdown=analysis_text,
            grounding_references=grounding_refs,
            search_queries_executed=search_queries,
        )

    @staticmethod
    def _extract_questions_from_markdown(markdown_text: str) -> List[str]:
        """Parse bulleted questions from the Investigative Questions section."""
        questions: List[str] = []
        in_questions_block = False
        for line in markdown_text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("### investigative questions"):
                in_questions_block = True
                continue
            if in_questions_block and stripped.startswith("### "):
                break
            if in_questions_block and (stripped.startswith("- ") or stripped.startswith("* ") or stripped[:2].isdigit()):
                cleaned = stripped.lstrip("-*0123456789. ").strip()
                if cleaned:
                    questions.append(cleaned)
        return questions[:5]

    @staticmethod
    def _extract_grounding_metadata(
        response: types.GenerateContentResponse,
        perspective_name: str,
        seed_queries: Optional[List[str]] = None,
    ) -> tuple[List[GroundingReference], List[str]]:
        """Extract web grounding chunks and search queries while preserving native character scripts and tagging origins."""
        references: List[GroundingReference] = []
        search_queries: List[str] = []
        if seed_queries:
            for sq in seed_queries:
                if sq and str(sq) not in search_queries:
                    search_queries.append(str(sq))
        seen_uris: set[str] = set()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            grounding_meta = getattr(candidate, "grounding_metadata", None)
            if not grounding_meta:
                continue

            web_queries = getattr(grounding_meta, "web_search_queries", None) or []
            for q in web_queries:
                if q and str(q) not in search_queries:
                    search_queries.append(str(q))

            chunks = getattr(grounding_meta, "grounding_chunks", None) or []
            for chunk in chunks:
                web_chunk = getattr(chunk, "web", None)
                if not web_chunk:
                    continue
                uri = getattr(web_chunk, "uri", None) or ""
                title = getattr(web_chunk, "title", None) or uri
                if uri and uri not in seen_uris:
                    seen_uris.add(uri)
                    references.append(
                        GroundingReference(
                            title=str(title).strip(),
                            uri=str(uri).strip(),
                            perspective_name=perspective_name,
                            snippet=f"Discovered via {perspective_name} grounding search.",
                        )
                    )

            supports = getattr(grounding_meta, "grounding_supports", None) or []
            for support in supports:
                segment = getattr(support, "segment", None)
                seg_text = getattr(segment, "text", "") if segment else ""
                chunk_indices = getattr(support, "grounding_chunk_indices", None) or []
                for idx in chunk_indices:
                    if isinstance(idx, int) and 0 <= idx < len(references) and seg_text:
                        if references[idx].snippet.startswith("Discovered via"):
                            references[idx].snippet = str(seg_text).strip()

        for ref in references:
            ref.origin_tag = detect_linguistic_origin_tag(
                f"{ref.title} {ref.snippet}",
                uri=ref.uri,
                perspective_name=perspective_name,
            )

        return references, search_queries
