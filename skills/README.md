# Pressroom Skills

Skills are Claude-powered processing steps. Each skill is a `.md` file containing instructions that Claude executes.

## Pattern

- A skill is a markdown file with clear instructions, steps, and output format
- Skills are invoked by the pipeline or manually by the editor
- Skills have access to tools declared in their file
- Skills can be chained: content_generator → humanizer → seo_geo

## Available Skills

| Skill | File | Purpose |
|-------|------|---------|
| Humanizer | `humanizer.md` | Remove AI-generated patterns from content |
| SEO + GEO Audit | `seo_geo.md` | Technical SEO + AI citation optimization |

## How the pipeline uses skills

The Python backend reads the skill `.md` file and passes it as the system prompt to Claude, along with the content to process. The skill's instructions define exactly what Claude does.

```python
# Example: invoke humanizer skill
skill_prompt = open("skills/humanizer.md").read()
result = claude.messages.create(
    system=skill_prompt,
    messages=[{"role": "user", "content": f"Voice context: {voice}\n\nContent to humanize:\n{content}"}]
)
```

## Adding a new skill

1. Create `skills/{name}.md`
2. Define: when to invoke, what it does, what tools it needs, output format
3. Wire it into the relevant pipeline step or expose it as a manual action in the UI
4. Document it in this README
