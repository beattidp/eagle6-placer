---
trigger: model_decision
description: "Apply whenever creating, modifying or updating code, and when creating or organizing documentation."
---

## Rules
* Never create source code artifacts or place design-specific documentation in the project root directory.
* If the project folder does not yet have a `doc/` directory, create it automatically before saving the file.
* If the project folder does not yet have a `src/` directory, create it automatically before writing code.

## Documentation & Worklogs
 - **Cite sources when referenced from the web**: if resources are referenced from web locations, cite the page and source of images, quoted prices, or other reference.
 - **Local copies of artifacts**: Place local copies of all proposals, implementation plans, walkthroughs and similar in `doc/`.
 - **Update documentation**: After each prompt and response, update relevant files in the `doc/` directory.
 - **Worklogs**: Maintain detailed activity logs in `doc/worklogs/`. Each entry must include the date, time, agent, and user, summarizing all actions and changes. Filenames for worklogs should be prepended with date as `YYYY-MM-DD_`.
 - **Feature & Fix Documentation**: Document all implemented, refined, or fixed features in `doc/features/` with comprehensive details on architecture, API usage, verification, or similar. Filenames for features should be prepended with serialized two digit number starting at '01_'.
 - **Plans & Walkthroughs (`doc/plans`, `doc/walkthroughs`)**: Place any planning documents or walkthrough documents in these folder locations respectively. Filenames should be prepended with date as `YYYY-MM-DD_`.
