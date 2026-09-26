/// <reference types="vite/client" />

// Build-time settings read via import.meta.env (see .env.example).
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}
