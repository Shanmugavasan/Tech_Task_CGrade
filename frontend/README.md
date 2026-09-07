# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  # Aviva AI Triage Dashboard

  This is the React frontend for the Aviva email triage prototype.

  ## Development

  From this directory:

  ```powershell
  npm install
  npm run dev
  ```

  The Vite development server runs on `http://localhost:5173` and expects the FastAPI backend at `http://localhost:8000`.

  ## Validation

  ```powershell
  npm run build
  npm run lint
  ```

  The dashboard includes the authenticated handler view, workload categories, thread actions, Q&A, drafts, audit history, notes, department filtering, and debounce controls. See the repository-level documentation in `../docs/` for the complete workflow.
])
