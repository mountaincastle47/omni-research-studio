"""Academic Protocol Resolvers: ArXiv and DOI Direct Paper & Metadata Fetch."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ARXIN_PATTERNS = [
    re.compile(r"https?://arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE),
    re.compile(r"https?://arxiv\.org/pdf/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?", re.IGNORECASE),
    re.compile(r"arxiv:(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE),
    re.compile(r"^(\d{4}\.\d{4,5}(?:v\d+)?)$"),
]

from core.paths import get_cache_dir

DOI_PATTERNS = [
    re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", re.IGNORECASE),
    re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", re.IGNORECASE),
]

ACADEMIC_CACHE_DIR = get_cache_dir() / "academic"


def extract_arxiv_id(text: str) -> Optional[str]:
    """Extract canonical ArXiv ID if present in text or URL."""
    clean = text.strip()
    for pattern in ARXIN_PATTERNS:
        match = pattern.search(clean)
        if match:
            return match.group(1)
    return None


def extract_doi(text: str) -> Optional[str]:
    """Extract canonical DOI string if present in text or URL."""
    clean = text.strip()
    for pattern in DOI_PATTERNS:
        match = pattern.search(clean)
        if match:
            return match.group(1)
    return None


def is_academic_identifier(text: str) -> bool:
    """Return True if the text represents an ArXiv paper or DOI identifier."""
    return extract_arxiv_id(text) is not None or extract_doi(text) is not None


class AcademicResolver:
    """Resolves academic papers via ArXiv API and CrossRef DOI API into full-text corpora."""

    @classmethod
    def resolve_arxiv(
        cls,
        arxiv_id: str,
        download_pdf: bool = True,
        output_dir: Optional[Path] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """Query ArXiv API for metadata and optionally download canonical PDF."""
        api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        resp = requests.get(api_url, timeout=timeout)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            raise ValueError(f"ArXiv ID '{arxiv_id}' returned no valid entry.")

        title_el = entry.find("atom:title", ns)
        title = re.sub(r"\s+", " ", title_el.text.strip()) if title_el is not None and title_el.text else f"ArXiv Paper {arxiv_id}"

        summary_el = entry.find("atom:summary", ns)
        summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

        published_el = entry.find("atom:published", ns)
        pub_year = published_el.text[:4] if published_el is not None and published_el.text else "Unknown"

        authors: List[str] = []
        for author in entry.findall("atom:author", ns):
            name_el = author.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        target_dir = output_dir or ACADEMIC_CACHE_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = target_dir / f"arxiv_{arxiv_id}.pdf"

        pdf_downloaded = False
        if download_pdf:
            try:
                pdf_resp = requests.get(pdf_url, timeout=30.0)
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                    pdf_path.write_bytes(pdf_resp.content)
                    pdf_downloaded = True
            except Exception:
                pass

        header_info = (
            f"# [ACADEMIC / PEER-REVIEWED] {title}\n"
            f"*Authors: {', '.join(authors) if authors else 'ArXiv Consortium'} | Year: {pub_year} | ArXiv: {arxiv_id}*\n\n"
            f"### Abstract / 초록\n{summary}\n\n---\n\n"
        )

        return {
            "title": f"[ACADEMIC / PEER-REVIEWED] {title}",
            "arxiv_id": arxiv_id,
            "authors": authors,
            "year": pub_year,
            "summary": summary,
            "abstract": summary,
            "pdf_url": pdf_url,
            "local_pdf_path": str(pdf_path) if pdf_downloaded else None,
            "header_markdown": header_info,
            "source_type": "academic_arxiv",
            "metadata": {
                "arxiv_id": arxiv_id,
                "authors": authors,
                "year": pub_year,
                "pdf_url": pdf_url,
                "downloaded_pdf": pdf_downloaded,
            },
        }

    @classmethod
    def resolve_doi(
        cls,
        doi_str: str,
        timeout: float = 12.0,
    ) -> Dict[str, Any]:
        """Query CrossRef API for DOI citation metadata and open-access links."""
        clean_doi = doi_str.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        encoded = urllib.parse.quote(clean_doi)
        api_url = f"https://api.crossref.org/works/{encoded}"

        headers = {"User-Agent": "OmniResearchStudio/1.0 (mailto:academic-grounding@omni.local)"}
        resp = requests.get(api_url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        data = resp.json().get("message", {})
        title_list = data.get("title", [])
        title = title_list[0] if title_list else f"DOI Publication ({clean_doi})"

        authors: List[str] = []
        for a in data.get("author", []):
            given = a.get("given", "")
            family = a.get("family", "")
            full = f"{given} {family}".strip()
            if full:
                authors.append(full)

        pub_date = (
            data.get("published", {})
            or data.get("published-print", {})
            or data.get("published-online", {})
            or data.get("issued", {})
            or data.get("created", {})
        )
        date_parts = pub_date.get("date-parts", [[]])[0] if isinstance(pub_date, dict) else []
        pub_year = str(date_parts[0]) if date_parts else "Unknown"
        journal = data.get("container-title", [""])[0] if data.get("container-title") else ""
        publisher = data.get("publisher", "")
        abstract = data.get("abstract", "")
        abstract_clean = re.sub(r"<[^>]+>", "", abstract).strip() if abstract else ""

        # Locate open-access PDF link if present
        pdf_link = None
        for link in data.get("link", []):
            if "pdf" in str(link.get("content-type", "")).lower():
                pdf_link = link.get("URL")
                break

        header_info = (
            f"# [ACADEMIC / PEER-REVIEWED] {title}\n"
            f"*Authors: {', '.join(authors) if authors else 'Scholarly Authors'} | Journal: {journal or publisher} | Year: {pub_year} | DOI: {clean_doi}*\n\n"
        )
        if abstract_clean:
            header_info += f"### Abstract / 초록\n{abstract_clean}\n\n---\n\n"

        return {
            "title": f"[ACADEMIC / PEER-REVIEWED] {title}",
            "doi": clean_doi,
            "authors": authors,
            "year": pub_year,
            "journal": journal,
            "publisher": publisher,
            "abstract": abstract_clean,
            "pdf_url": pdf_link,
            "header_markdown": header_info,
            "source_type": "academic_doi",
            "metadata": {
                "doi": clean_doi,
                "authors": authors,
                "year": pub_year,
                "journal": journal,
                "publisher": publisher,
                "pdf_url": pdf_link,
            },
        }

    @classmethod
    def resolve(
        cls,
        identifier_or_url: str,
        download_pdf: bool = True,
    ) -> Dict[str, Any]:
        """Polymorphic resolver for any ArXiv URL/ID or DOI."""
        arx = extract_arxiv_id(identifier_or_url)
        if arx:
            return cls.resolve_arxiv(arx, download_pdf=download_pdf)

        doi = extract_doi(identifier_or_url)
        if doi:
            return cls.resolve_doi(doi)

        raise ValueError(f"Unrecognized academic identifier: {identifier_or_url}")
