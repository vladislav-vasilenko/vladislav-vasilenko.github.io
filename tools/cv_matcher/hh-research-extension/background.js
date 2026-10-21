/* MV3 bootstrap. Order is explicit: shared cores → browser tools → workers.
 * Workers register their own messages/alarms; they do not import this entry point.
 */
const activeJobs = new Set();
importScripts(
  "core.js", "resume-core.js", "catalog-core.js", "resume-import-core.js",
  "hh-crawl-core.js", "board-core.js", "board-adapters.js", "board-widget-core.js"
);
importScripts("browser-navigation.js", "resume-worker.js");
importScripts("local-service.js", "archive-sync-core.js", "collection-storage.js");
importScripts("hh-crawl.js", "archive-sync.js", "company-settings-sync.js", "board-crawl.js");
importScripts("hh-badges-background.js");
importScripts("hh-apply-core.js", "hh-connection.js", "resume-bump-worker.js", "hh-workflow.js");
importScripts("career-workflow.js", "discovery-worker.js", "resume-intake-worker.js");
importScripts("diagnostics-core.js", "diagnostics-worker.js");

importScripts("hh-sync-core.js", "hh-cleanup-core.js", "hh-cleanup-worker.js");
