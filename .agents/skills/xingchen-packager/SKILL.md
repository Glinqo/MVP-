# Xingchen Packager Skill

Use this skill when preparing content for iFlytek Xingchen workflow import or copy-paste setup.

## Steps

1. Check `xingchen/workflow_node_configs.md`.
2. Ensure every workflow node has a matching prompt or code file.
3. Put copy-ready snippets into `xingchen/copy_paste_pack.md`.
4. Keep variable names consistent across docs and prompts.
5. Verify sample input and output with `tests/sample_inputs.json`.

## Do Not

- Do not assume a custom deployment pipeline.
- Do not require npm packages or build tools.
- Do not hide scoring rules inside natural language prompts.

