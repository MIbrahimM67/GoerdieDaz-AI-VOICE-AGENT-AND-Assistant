# How to Revert to OpenAI Production

## Option 1: Git Tag (Recommended — full revert)
```bash
git checkout openai-production
```
This restores the ENTIRE codebase to the exact state before the open-source swap.

## Option 2: Env Var Toggle (If code supports both modes)
In `.env`, change:
```env
LLM_PROVIDER=openai
```
Then redeploy. No code changes needed.

## Option 3: Manual File Restore
Copy these files from `_openai_backup/` back to their original locations:
```
_openai_backup/handler.py             → app/ws/handler.py
_openai_backup/embedding_service.py   → app/services/embedding_service.py
_openai_backup/memory_service.py      → app/services/memory_service.py
_openai_backup/session_summary_service.py → app/services/session_summary_service.py
_openai_backup/config.py              → app/config.py
```

## Files Backed Up
| File | Purpose |
|------|---------|
| `handler.py` | OpenAI Realtime WS voice pipeline |
| `embedding_service.py` | text-embedding-3-small embeddings |
| `memory_service.py` | gpt-4o-mini fact extraction |
| `session_summary_service.py` | gpt-4o-mini session summaries |
| `config.py` | Settings with OpenAI-only config |

## Git Tag
- Tag: `openai-production`
- Pushed to: `origin/openai-production`
- Commit: The last commit before open-source swap
