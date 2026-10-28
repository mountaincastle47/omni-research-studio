"""Forensic Root-Cause Audit Summary for OmniSweep Perspective Reports Translation Cache Miss."""

def print_diagnostic_summary():
    print("""
================================================================================
=== FORENSIC ROOT-CAUSE AUDIT: OMNISWEEP PERSPECTIVE TRANSLATION CACHE MISS ===
================================================================================
1. Location 1: ui/main_window.py:1162-1168 (_on_language_changed)
   - Code pattern:
       elif self.current_language == "ko":
           if self.synthesis_translated_text:
               ...
           elif self.synthesis_original_text and self.active_worker is None:
               self._start_translation(self.synthesis_original_text, target_pane="synthesis")

           if self.perspective_translated_text:
               ...
           elif self.perspective_original_text and self.active_worker is None:
               self._start_translation(self.perspective_original_text, target_pane="perspective")
   - Root Cause A (Worker Collision & Starvation):
     When synthesis report translation starts, self._begin_task() assigns self.active_worker = worker.
     Immediately at line 1166, the condition `self.active_worker is None` evaluates to False.
     Consequently, perspective translation is completely dropped and never triggered.
   - Root Cause B (Synchronous In-Memory Cache Lookup Omission):
     Line 1162 checks only the local variable `self.perspective_translated_text`. If this string is empty
     (e.g., initial language toggle, fresh workspace tab, or loaded project), it does NOT synchronously query
     the thread-safe CacheManager (self.cache_manager.get_translation(hash, 'ko')) or the active workspace pane.
     It needlessly falls through to spawning an asynchronous QThread worker.

2. Location 2: ui/main_window.py:1321-1326 (_on_toggle_perspective_language_view)
   - Code pattern:
       if self.perspective_translated_text:
           ...
       elif self.perspective_original_text and self.config_manager.has_api_key():
           self._start_translation(self.perspective_original_text, target_pane="perspective")
   - Root Cause:
     Missing synchronous cache validation against CacheManager before dispatching _start_translation.

3. Location 3: ui/workspace_tabs.py:238-240 and core/project_manager.py:46-48
   - Missing per-perspective structured caching architecture:
     Neither WorkspaceReportPane nor WorkspaceTabState maintained per-perspective translation entries
     (e.g., perspectives[p_id]["content_ko"] and perspectives[p_id]["content_en"]).
     Unlike synthesis which implements set_translated_synthesis(), WorkspaceReportPane lacked
     set_translated_perspective() and get_perspective_translation().

4. Location 4: ui/main_window.py:1571-1577 (_on_translation_finished)
   - In target_pane == "perspective", translation output was set only on the main window property;
     it was never saved back to WorkspaceReportPane or per-perspective data structures via a dedicated
     setter, causing cache loss across workspace tab switches and session restorations.
================================================================================
""")

if __name__ == "__main__":
    print_diagnostic_summary()
