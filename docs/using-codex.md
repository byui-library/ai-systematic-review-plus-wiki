# Using Codex (or another AI assistant)

The template doesn't depend on any one AI tool. All of the instructions an assistant needs are plain Markdown files:

- **`AGENTS.md`** is read automatically by Codex and most other coding agents. It is identical to `CLAUDE.md`, which Claude Code reads.
- **`prompts/01-…06-*.md`** are the playbooks for each task (setup, classify, paper summaries, concepts and debates, appraisal, sub-reviews).
- Every step that changes data goes through `py run.py …`, which checks the assistant's work before saving it.

## With Codex

1. Open your copy of the template as the working folder in Codex (CLI, IDE extension, or app).
2. Ask in plain words, for example *"set up my review"*, *"classify the next batch"*, *"summarise the papers"*. Codex finds the matching playbook through `AGENTS.md`.
3. When it saves classifications, it records its own tool and model name, for example `--tool "Codex" --model "<model id>"`. These go into the audit log and the AI-use disclosure.

## With other agents

Any assistant that can read files and run terminal commands in the folder can run the review. If it doesn't read `AGENTS.md` by itself, start with: *"Read AGENTS.md and follow it."*

## Switching assistants mid-review

That's fine. Decisions are saved with the tool and model that made them, and the AI-use disclosure lists every tool used. Screening stays consistent because both assistants follow the same playbooks and the same prompt, which is built from your `project.yaml`.
