# PHASE-SKILLS

This optional repo-local profile describes how phase-skills talks with the user and asks for decisions in this repository.

If it is absent, phase-skills uses default behavior. If it is present, `/phase-init`, `/phase-run`, reviewers, and workers use this file to tune explanation style and option presentation.

## Purpose

`PHASE-SKILLS.md` is not an autonomy policy. The phase-skills harness and each phase spec continue to own which changes may be applied automatically and which risks must escalate to the user.

This file adjusts only the communication and decision interface profile.

- How to explain work plans.
- Whether to prioritize logic, policy, and pseudocode before code.
- How to present options and recommendations when user decisions are needed.
- How much implementation detail to expose.

## Profile

```yaml
preset: guided-vibe-coder

communication_profile:
  planning_representation: pseudocode # plain | pseudocode | flow | table | story
  analogy_mode: ask                   # off | ask | on
  explanation_depth: detailed         # brief | normal | detailed
  code_detail_level: low              # low | medium | high

decision_interface:
  format: options_with_recommendation # options_with_recommendation | concise_options | question_first
  include_tradeoffs: true
  avoid_raw_code_as_primary_explanation: true

language:
  user_facing: ko                   # auto | ko | en
  planning_artifacts: ko            # auto | ko | en
  internal_protocol: en               # en only
  preserve_structural_tokens: true
```

### Language

`language` adjusts which language is used for user-visible explanations and planning artifact bodies. It does not affect autonomy, scope, risk gates, or git policy.

`auto` chooses language in this order:

1. Explicitly configured value.
2. Current user input language.
3. Existing task artifact language.
4. repo fallback

`internal_protocol` currently supports only `en`. When `preserve_structural_tokens: true`, structural tokens such as harness marker, YAML key, enum value, command, path, anchor, and parser label are not translated.

## Presets

Changing `preset` alone records the preferred profile name only. It does not rewrite the other fields automatically, so local overrides remain stable.

To adopt a preset's recommended values, run `/phase-config apply-preset-values` after changing `preset`, or choose the equivalent explicit helper action. Recommended preset values are maintained by the phase-config helper, not by duplicating a separate table in this template.

### guided-vibe-coder

Default. Fits a flow where judgment focuses on logic, policy, and pseudocode before code details, with AI leading implementation details.

### product-logic

Explains policy, flows, requirements, and edge cases first. State transitions and product rules come before implementation files.

### developer

Explains code, files, tests, and API contracts first. Implementation details and verification commands are exposed more directly.

## Non-Goals

The user profile must not relax or bypass these criteria:

- destructive change
- security or permission changes
- cost increases
- new external service dependencies
- UX/API meaning changes
- product policy choices

These items continue to be judged by phase-skills harness risk criteria and escalate to user decision when needed.

## Relation to AGENTS.md

`AGENTS.md` defines repository work rules, commands, scope, tests, and commit rules.

`PHASE-SKILLS.md` adjusts how phase-skills explains those rules and asks the user for decisions. If the two files conflict, `AGENTS.md` and the phase spec win because they contain work-safety and repository rules.
