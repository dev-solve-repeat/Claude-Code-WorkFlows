import { defineConfig } from "@trigger.dev/sdk/v3";

export default defineConfig({
  project: "proj_recxlbcytjvdiywsileo",
  dirs: ["src/trigger"],
  maxDuration: 300, // 5 minutes — enough time to search + post 10 leads
});
