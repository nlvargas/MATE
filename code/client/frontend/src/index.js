// Webpack's entry point. App.js does the actual `render(<App />, ...)` call
// as an import-time side effect (see its bottom), so this import is only
// here to pull that side effect in -- App itself is never referenced.
// eslint-disable-next-line no-unused-vars
import App from "./App";
