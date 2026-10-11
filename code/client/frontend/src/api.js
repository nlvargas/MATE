// Builds a backend URL from a path like "/upload/". The prefix comes from the
// server (frontend/views.py's index(), via window.__MATE_CONFIG__.apiBase):
// "/dev" for a local runserver, "" on the deployed custom domain, the stage
// name on the default execute-api URL. Hardcoding "/dev" here made every API
// call 404 on the custom domain.
export function apiUrl(path) {
  const base = (window.__MATE_CONFIG__ && window.__MATE_CONFIG__.apiBase) || "";
  return base + path;
}
