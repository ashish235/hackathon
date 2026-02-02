/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string = "http://localhost:8082";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
