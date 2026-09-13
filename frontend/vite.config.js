import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    __VERCEL_API_PROXY__: JSON.stringify(process.env.VERCEL === "1"),
  },
});
