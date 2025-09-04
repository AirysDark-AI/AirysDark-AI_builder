# AirysDark-AI Builder Bundle

Included:
- tools/AirysDark-AI_builder.py (renamed from ai_autobuilder.py, identity updated)
- tools/AirysDark-AI_detector.py (detector that writes AirysDark-AI_{type}.yml workflows and calls the new builder)
- .github/workflows/AirysDark-AI_detector.yml (bootstrap to run the detector and open a PR)
- .github/workflows/ai-autobuilder-android.yml (reusable Android workflow - calls new builder)
- .github/workflows/ai-autobuilder-universal.yml (reusable universal workflow - calls new builder)

Secrets to set in your repo:
- BOT_TOKEN: bot PAT with Contents:write, Pull requests:write
- (optional) OPENAI_API_KEY: OpenAI key (fallback to llama.cpp otherwise)

Usage:
1) Commit this bundle to your repo.
2) Run the 'AirysDark-AI_detector' workflow to generate per-type workflows (AirysDark-AI_android.yml etc.).
3) Or call the reusable workflows from other repos with 'secrets: inherit'.
