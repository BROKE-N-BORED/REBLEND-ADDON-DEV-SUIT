# Reblend Add-on Dev Suite — Project Dossier

**Status:** Dossier v0.13. Phase 1 suite side complete (manifest validator + secrets scan + manifest writer); Phase 2 built and verified (chat loop backend, project model, Surprise template, Qt chat window); Phase 4 built and verified — both emitters (Reblend `.rblpack` + installer, Blender extension zip + legacy `bl_info` fallback) and the pack window, pulled forward while Phase 3 waits on the loader — see the build-sequence note in §12. The Library window (§6.9), the Blender drive + test window (Phase 5), and Phase 6 (command palette, How to Use index, measurements strip, GUI installer + uninstaller, §13 verification round, silent update check, uninstall menu entry) are built and verified too. 449 tests green (Qt venv; 372 + 24 skipped on system python). Phase 3 (Reblend render + test windows) waits on the loader from the REBLEND DEV thread. The icon is designed with Joshua. Repo: BROKE-N-BORED/REBLEND-ADDON-DEV-SUIT (Joshua created it 2026-11-18; first push and first release v0.1.0 the same day). This dossier is the full-stack plan, written first so Joshua can read it, correct it, and sign it off. v0.2 answered all ten §15 decisions from evidence he already gave; the build proceeds on his word.

**Date:** 2026-11-17
**Author:** Arlo, for Joshua Lofland
**Thread:** REBLEND ADDON DEV SUITE (side chat `471b5cca`)
**Version:** Dossier v0.13 (v0.1, 2026-11-17 morning, asked the decisions; v0.2, 2026-11-17, answers them from evidence; v0.3, 2026-11-17, states the §5.1 validation rules and reconciles the manifest validator to them; v0.4, 2026-11-17, records the build-sequence note in §12; v0.5, 2026-11-17, states the §5.1 flat-import rule and the §5.4 emitter mapping; v0.6, 2026-11-17, states the §5.3 Blender relative-import rule; v0.7, 2026-11-17, adds `contributions` to the project model in §5.4/§9.4; v0.8, 2026-11-17, adds the shelf record to the data model in §9.4; v0.9, 2026-11-17, records the §13 verification round (guard tests, fresh-tree verification, three defects fixed in place); v0.10, 2026-11-17, adds §9.7, the silent update check (standing order); v0.11, 2026-11-18, adds the uninstall menu entry (the installer ships in the installed distribution); v0.12, 2026-11-18, records the no-terminal standing rule in §12; v0.13, 2026-11-18, records the repo (SUIT, Joshua's spelling), the first push (28b44b94), the first release v0.1.0, and the update check verified against the real release)

---

## How to read this dossier

- **Sections 1–3** are the idea and the feel. Read these and you know what it is.
- **Sections 4–5** answer the first question the Reblend plan left open (§8): what an add-on pack *is*, in Reblend terms and in Blender terms.
- **Sections 6–8** are the workstation itself: the windows, the AI chat, and the render and test windows.
- **Sections 9–10** are the full stack: architecture, data, and the design system traced to the source files.
- **Sections 11–12** are what gets built first, and in what order.
- **Sections 13–14** are how it gets verified, and what could go wrong.
- **Section 15** is the decisions, answered from evidence in v0.2. Any of them can change on his word.

A word on scope: the Reblend plan (§8, 2026-11-16) recorded the suite as Reblend-only. On 2026-11-17 Joshua ordered this dossier with **Blender added as a second target**: the suite makes add-ons for Reblend *or* Blender. That expansion is his call, recorded here, and the whole dossier is built around it: one authoring core, two exporters.

## Sources this dossier is built from

| Source | What it is | How it was used |
|---|---|---|
| `Modern_UI_Design_Techniques_0_5hwj.md` (uploaded 2026-11-17) | The 12-technique drawer, researched 2026-11-13 | Technique picks in §10. Note: this upload is the **older copy** — its filter Q4 still reads "Does it do something real? No decoration for its own sake." That line was struck 2026-11-13 (it was Arlo's note, not Joshua's rule). The dossier uses the corrected Q4: "Does it make the app feel like itself?" |
| `Design_Philosophy_and_Rules_1_nseq.md` (uploaded 2026-11-17) | Philosophy (Part 1) + rules U1–U33 (Part 2) | Philosophy and rules in §10. Note: this upload is the **older 2-part version** — it is missing U34–U39, D3, and Part 3. The dossier uses the current 3-part rules. |
| `Design_Rules_2_jx67.md` (uploaded 2026-11-17) | Rules-only copy, U1–U33 | Cross-check only. Same older snapshot as above; nothing new in it beyond the other two uploads. |
| `~/workspace/design-rules.md` (578 lines, 3 parts) | Current working copy of the rules | The authority where the uploads are stale. Source of truth is the BNB UI Design Source File Library repo. |
| BNB UI Design Source File Library (72 entries) | The encyclopedia library, source of truth for all UI work | Entry-level guidance in §10, cited by entry number (010, 003, 012, 066, 043, and others). |
| `~/workspace/reblend/ui-reorganization-plan.md` §8–§9 | The Dev Suite vision and the add-on list | §8 is the suite's origin; §9 is the first-target list (§11). |
| `~/workspace/reblend/ui-audit-and-redesign-tasks.md` | PO8, PO9, PO10, PO11 definitions | First-target specs (§11). |
| `~/workspace/reblend/physics-particles-enhanced-design.md` | T25/T26/T27 water and fluid designs | T26/T27 first-target specs (§11). |
| Reblend tree (`reblend-v02-ffire-build/reblend/light_engine/`, 13,506 lines) | The live engine: scene, viewport, window, shaders, textures, particles | Grounds the Reblend render window (§8) and the pack API (§5). There is no plugin system in the tree today — that gap is the dossier's central design problem. |
| Blender Manual, add-on tutorial (docs.blender.org) + Blender Python add-on references, checked 2026-11-17 | `bl_info`, `register()`/`unregister()`, `bpy.types.Operator` / `Panel` / `PropertyGroup`, `blender_manifest.toml` (4.2+ extensions) | Grounds the Blender exporter (§5). Blender 5.0 shipped November 2025; the suite targets the extensions format first, with the legacy format as a fallback. |
| `~/workspace/reblend/repos-for-project-development.md` | The repo catalog Joshua distributed 2026-11-15 | BNB system applies to this build like every build (§9, §12). His rules win on any conflict. |

Nothing in the three uploads was new versus the current rules and library — they are the same material at an older revision. Nothing was lost by using the current versions; the dossier says where the uploads differ so the record is honest.

---

## 1. The idea in one page

**One sentence:** Talk to the suite in plain words, watch it build an add-on, see the add-on working in a real 3D render window, test it, and pack it for Reblend or Blender — without ever opening a terminal, reading API docs, or hand-writing plugin boilerplate.

**Who it is for:** Joshua, personal use. One user. He has ideas for tools, brushes, materials, and simulations; the suite turns an idea into a working pack. It is not a marketplace, not a store, not a collaboration tool. One person, one PC, his ideas.

**The problem it solves:** Making an add-on today means knowing the plugin API, the file layout, the registration dance, the UI toolkit, and the test loop — before you write one line of the actual idea. Blender's side alone is a `bl_info` dict, `register()`/`unregister()` pairs, operators, panels, property groups, and a manifest file, all of which must match or the add-on silently fails to load. Reblend's side is worse: there is no plugin format at all yet, so there is not even anything to learn. The suite absorbs all of that. Joshua describes what the add-on should do; the suite writes the boilerplate, wires the registration, shows the result rendering live, runs the tests, and packs the file.

**The shape of the answer:** A native Linux desktop workstation (Python + PySide6, like Reblend). One function per window. The chat window is the front door: prompt-first, streaming, plan shown before anything is built. Render windows show the add-on working in a real scene. A test window runs checks and reports in plain words. A pack window builds the finished file and installs it where it belongs. The backend configures itself for his PC; the measurements are shown live like science software; the user never sets a training rate or a render budget by hand.

**The test it must pass:** A child could open it, say "make the water splash when the ball drops in," and watch it happen — without a manual, without a terminal, without knowing what an add-on is. That is the toy bar (U34), and it is the bar for every window in this dossier.

**What it costs:** $0. Local models through Ollama, no paid APIs, no cloud, no subscriptions. The suite never phones home, never needs an account, and never puts a secret in code.

---

## 2. What it is, and what it is not

### What it is

- A **separate program** from Reblend. Reblend stays lean; the suite is the workshop where packs get made. (Plan §8.)
- An **AI chat interface workstation** for authoring add-ons. Chat is the primary way work gets done, not a help box bolted onto an editor.
- A **dual-target authoring tool**. One add-on project, two outputs: a Reblend pack (`.rblpack`) and a Blender add-on (extension package). The authoring core is shared; the exporters are target-specific (§4–§5).
- A **render-and-test bench**. Rendering windows are part of the program, not an external step: the Reblend render runs live in-process, and Blender test renders come back into the suite (§8).
- A **pack builder**. Manifest, version, icon, files, install — the suite assembles the finished pack and puts it where Reblend or Blender will find it.
- A **personal tool**. Built for one user on one 8 GB Mint PC with no GPU. Every performance decision in this dossier is measured against that machine.

### What it is not

- **Not Reblend.** No modeling, no scene editing, no rendering features beyond what testing an add-on needs. If a feature belongs in Reblend, it gets built in the REBLEND DEV thread, not here.
- **Not a code editor.** There is a code window (§6.5) for reading and fixing what the AI wrote, but the suite is not trying to be a general editor. No plugins for the suite itself, no extension marketplace.
- **Not a Blender replacement or a Blender clone.** The suite drives Blender as a test target; it does not reimplement Blender, and it does not embed Blender's live window (see §8.3 for the honest reason).
- **Not a store or a sharing platform.** Packs are Joshua's. If he ever wants to publish or share a pack, that is a decision for later (§15, D10), not a feature of v1.
- **Not cloud software.** No account, no sync, no remote build. Everything runs on his PC. If the WiFi is off, the suite still works (after first install).
- **Not a second Code Forge.** Forge is a general coding agent; the suite is a specialist. It knows one job — add-ons for two 3D apps — and every window, tool, and check is shaped to that job. Where Forge's patterns apply (plan before build, approval before file writes, visible tool calls), the suite reuses them; it does not reimplement Forge.

### Scope boundaries that matter

- **The Reblend pack loader is not this program.** Reblend itself must learn to load packs: a loader plus a plugin API in the Reblend tree. That work belongs to the REBLEND DEV thread, and it gates the suite's Reblend testing (§12, Phase 1). This dossier defines the format the loader must implement (§5.1) so the two threads agree on paper first.
- **The Blender add-ons the suite makes are standard Blender add-ons.** Nothing proprietary, nothing that only works with the suite. A pack the suite builds for Blender installs in Blender the normal way, by hand, even if the suite is never opened again.
- **No limits are invented anywhere in this dossier.** No cap on projects, packs, test runs, chat length, render count, or file size. Where a number appears (a default, a budget, a timeout), it is a measured default the backend sets for his machine, changeable, and flagged as such. A limit needs Joshua's say-so (standing rule, 2026-11-15), and this dossier asks for none.

---

## 3. How it feels to use

### 3.1 The five-minute story

Joshua opens the suite. The Home window shows his projects as cards: one big card for the current project, small cards for the rest. He clicks **New add-on**. The suite asks one thing: *what should it do?* — in plain words, one box, nothing else on screen (U21: ask for the minimum up front).

He types: "make water that splashes when things drop in."

The chat window opens. The AI answers in plain words with a short plan — what it will build, which target it is for, what the test scene will show — and waits. Nothing is built yet. He taps **Build it**.

He watches the work happen: the chat streams, the file list grows, each step named as it runs (U16: always show what it is doing). When the code is ready, the Reblend render window opens on a test scene — a tank, a ball above it — and the ball drops, and the water splashes. He can see it. If it looks wrong, he says so in chat ("bigger splash, slower fall") and the AI changes it and re-renders. When it looks right, he taps **Test**. The test window runs the checks and reports in plain words: loads clean, unloads clean, undo works, no crash on the test scenes, runs at a measured frame rate on this PC. Then he taps **Pack**. The pack window shows the finished file, its version, its icon, and one button: **Install in Reblend**. Done. The whole loop — idea to installed pack — happened inside one program, without a terminal, without a docs page, without touching boilerplate.

That is the bar. Every section below exists to make that story true.

### 3.2 The three journeys

**Journey A — A new Reblend add-on from an idea.** The story above. Chat → plan → build → see it render → test → pack → install in Reblend. The suite picks the Reblend target because the idea is a Reblend-shaped one (or because he picked Reblend on the New screen — one tap, no default selected, U6). The first targets in §11 are all Journey A.

**Journey B — A new Blender add-on from an idea.** Same front door, different back end. He types the idea, the AI builds a standard Blender extension package, and the Blender test window shows the result: the suite drives Blender in the background, runs the add-on against a test scene, and brings back renders and a plain-words report (§8.3). He installs it into Blender from the pack window, or takes the zip and installs it by hand — it is a normal Blender add-on either way.

**Journey C — Fix or improve a pack that already exists.** He opens a project from Home. The chat knows the project: its files, its last test run, its last pack. He says "the splash is too small on the big tank" and the AI finds the right value, changes it, re-renders, and shows the before and after side by side. Or a test fails after a Reblend update, and the chat explains what broke in plain words and offers the fix. Nothing is ever rebuilt from scratch unless he asks; the AI edits surgically (U8), and every change is a proposal he approves before it lands (§7.4).

### 3.3 What the user never has to do

- Never write `register()` / `unregister()` by hand. Never write a manifest by hand. Never hand-place a file in a Blender scripts folder.
- Never read API docs to start. The chat knows both APIs; the How to Use index (U22) explains the suite, not the APIs.
- Never use a terminal. Install, run, test, pack, and install packs are all clicks (U3).
- Never guess whether something is working. Every long job shows progress, a live status line, and a cancel button (U16, U26).
- Never lose work to an experiment. The render windows run on test scenes and playground copies; the real project is untouched until he says so (entry 066).
- Never wonder what the AI changed. Every change is listed, diffed, and undoable (§7.4).

---

## 4. The two targets: one core, two exporters

Reblend and Blender are different programs with different plugin systems. The suite does not pretend they are the same. It shares what is genuinely shared — the idea, the project, the chat, the tests that are target-free — and keeps the target-specific parts honest and separate.

| | Reblend pack | Blender add-on |
|---|---|---|
| **Format** | `.rblpack` (a zip) — defined by this dossier, §5.1. New; no loader exists yet. | Standard Blender extension package — `__init__.py` + `blender_manifest.toml` (Blender 4.2 and later, including 5.x). Legacy `bl_info` single-file form available as a fallback. |
| **Language** | Python (same as Reblend itself). | Python (Blender's `bpy` API). |
| **Entry point** | `addon.py` with `register(api)` / `unregister(api)`. | `__init__.py` with `register()` / `unregister()`, classes registered via `bpy.utils.register_class`. |
| **UI it can add** | Wheel pages and wheel slices, inspector sections, menu items, panels, brushes, material families and styles. | Operators, panels, menus, property groups. |
| **Engine hooks** | Scene objects, materials, particles, viewport draw, animation frames, undo stack. | Scene data, objects, meshes (`bmesh`), modifiers, render hooks — through `bpy`. |
| **How it installs** | Dropped into Reblend's packs folder by the suite (or by hand). Reblend's loader scans the folder at startup. | Installed through Blender's Extensions preferences, or dropped into Blender's add-ons folder. The suite can place the file; Blender enables it. |
| **How it is tested in the suite** | Live, in-process: the real Reblend viewport runs inside the suite (§8.2). | Driven: the suite runs Blender in background mode with a test script and brings back renders and logs (§8.3). |
| **What the author writes** | The idea: behavior + UI contributions, in the suite's project form. | The same idea, expressed through the Blender emitter. |
| **What the suite writes** | Manifest, entry boilerplate, registration, packaging. | Manifest or `bl_info`, entry boilerplate, class registration, packaging. |

### The shared authoring model

A suite project is target-free at its heart: a name, a description, the behavior (code), the UI contributions (what it adds and where), the assets (icons, textures, presets), and the tests (what "works" means). Each target has an **emitter**: a backend that turns the project into that target's real files. The Reblend emitter writes a `.rblpack`; the Blender emitter writes an extension package.

Some things map cleanly across both targets (an operator that acts on the selected object; a panel with a few controls; a randomize button). Some things do not: Reblend's wheel has no Blender equivalent, and Blender's modifier stack has no Reblend equivalent. The suite never fakes a mapping. Target-specific parts are marked as such in the project, the chat says so in plain words when an idea only fits one target, and the pack window shows which targets a project supports before it builds. A project can be Reblend-only, Blender-only, or both — the author's choice, made per project, changeable later.

### What the suite never does across targets

It never converts a finished Reblend pack into a Blender add-on by rewriting it behind the author's back, and never the reverse. The two emitters share the project, not each other's output. If an idea needs both targets, the chat builds both from the shared project and tests each on its own target.

---

## 5. What an add-on pack is

This is the question plan §8 left open, and the dossier's central design. The answer has three parts: the Reblend pack format (new, defined here), the Blender output (standard, followed faithfully), and the shared project the suite authors.

### 5.1 The Reblend pack format, v1 (proposed)

A Reblend pack is a zip file with the extension `.rblpack`. It is plain files inside — no compilation, no binary step — so a pack can be opened, read, and fixed with ordinary tools.

**Contents:**

```
surprise-pack.rblpack (zip)
  manifest.json        The pack's identity and contributions (below)
  addon.py             Entry point: register(api) / unregister(api)
  code/                The pack's own modules (any layout; imported as a package)
  assets/              Icons, presets, textures, test scenes shipped with the pack
  README.md            Plain-words description, shown in Reblend's pack list
  icon.png             The pack's icon (shown in the wheel and the pack list)
```

**`manifest.json` (the whole contract):**

```json
{
  "id": "surprise",
  "name": "Surprise",
  "version": "1.0.0",
  "description": "Randomize a material for inspiration. One button, one undo step.",
  "author": "Joshua Lofland",
  "reblend": ">=0.2",
  "entry": "addon.py",
  "icon": "icon.png",
  "contributions": {
    "wheel": [
      { "page": "Style", "slot": "bottom-row", "label": "Surprise", "action": "surprise.randomize" }
    ],
    "menu": [],
    "inspector": [],
    "brushes": [],
    "materials": [],
    "simulations": []
  },
  "permissions": {
    "files": "project-only",
    "network": false
  }
}
```

**Rules of the format:**

- **Identity.** `id` is lowercase, no spaces, unique per pack. `version` is three numbers (major.minor.patch). The loader refuses a pack whose `reblend` range does not cover the running Reblend version, and says so in plain words instead of failing silently.
- **Contributions, not hooks by luck.** A pack declares what it adds — wheel slots, menu items, inspector sections, brushes, material families, simulations — in the manifest. Reblend renders exactly what is declared, and nothing else. An undeclared UI addition is not a feature; it is a bug the loader reports.
- **Entry point.** `addon.py` defines `register(api)` and `unregister(api)`. `register` receives the plugin API object (§5.2) and wires the pack up; `unregister` removes everything it added, in reverse. Everything registered must be unregistered — the test harness checks this (§8.4).
- **Permissions.** A pack declares what it needs. `files: project-only` means it reads and writes inside the project and its own folder only. `network: false` is the default and the only value in v1: packs do not touch the network, full stop. A pack that needs more than v1 allows does not get a quiet exception; the format grows by a versioned change, with Joshua's say-so.
- **No secrets, ever.** A pack contains no keys, tokens, or credentials (immutable secrets rule). The pack builder scans for secret-shaped values before packing and refuses to pack a file that looks like it holds one, naming the file.
- **The base never depends on a pack.** Reblend runs exactly the same with zero packs installed. A pack that fails to load is reported in the pack list with its error in plain words, and Reblend keeps running. A pack can never take Reblend down at startup: load failures are caught per pack, and the pack is left disabled.
- **Install and uninstall are file operations.** Install: copy the `.rblpack` (or its unzipped folder) into Reblend's packs folder. Uninstall: delete it. No registry, no installer inside the pack, no code that runs at install time. The suite's pack window does the copying; doing it by hand works identically.
- **Imports inside a pack (v0.5).** A pack's modules are imported by flat name (`import pick`, not `import code.pick`): the loader puts the pack's `code/` folder on the import path when it loads `addon.py`. In the project, the same code lives under `src/reblend/` and `src/shared/` (§5.4) and is imported the same flat way — the test harness puts both folders on the path. Module names must be unique across `src/reblend/` and `src/shared/` inside one project (the emitter refuses a project where two files would land on the same name in `code/`), and the loader loads each pack's modules in isolation, so two packs can both have a module called `pick` without colliding.

**Validation rules (v0.3 — what the suite's validator and Reblend's loader both enforce).** Required fields: `id`, `name`, `version`, `reblend`, `entry`, `contributions`. `id` starts with a letter or digit and uses only lowercase letters, digits, dashes, and dots. `version` is three numbers (`1.0.0`). `reblend` is a non-empty version requirement string such as `>=0.2`; the loader enforces the range, the validator checks it is present and written as text (a range grammar is a later item). `entry` is a file name on its own (no folders) ending in `.py`, and the file must sit beside the manifest at the pack root. `contributions` maps a known kind — `wheel`, `menu`, `inspector`, `brushes`, `materials`, `simulations` — to a list of objects; an unknown kind is an error, and every wheel entry needs a `label` and an `action`. Optional: `description`, `author`, `icon` (text when present). `permissions`, when present, is an object: `network` must be `false` (the only value in v1) and `files` must be `project-only` (the only value in v1). Unknown top-level fields are ignored, so a newer pack still reads in an older suite. Every failure is reported in plain words; nothing about a bad manifest ever crashes the suite or Reblend.

### 5.2 The Reblend plugin API (what `register(api)` gets)

The API object is the pack's only way into Reblend. It is deliberately narrow in v1 and grows by versioned additions, never by packs reaching around it into Reblend's internals.

| Area | What a pack can do in v1 |
|---|---|
| Scene | Read the scene; find objects by id; add objects; change an object's material, transform, and visibility. All changes go through the undo stack — one pack action is one undo step. |
| Materials | Read the selected object's material; apply a material by family/style/layout; read and set knob values; register a material family or style. |
| Wheel | Add a page, a slice, or a bottom-row button (as declared in the manifest). |
| Panels and menus | Add a menu item or an inspector section (as declared). |
| Brushes | Register a brush (scatter, sculpt, paint) with radius, strength, and falloff. |
| Simulation | Register a per-frame step function (for water, particles, physics extras) with a plain name shown in the timeline. |
| Viewport | Draw an overlay (guides, gizmos, highlights) in the viewport's draw pass. |
| Files | Read and write inside the project folder and the pack's own folder. |
| UI feedback | Show a status line, a progress bar with cancel, and a plain-words error. |

What a pack **cannot** do in v1: touch the network; read or write outside its folders; replace Reblend's menus, wheel, or settings; run code at install time; change another pack's files; hide its own errors. Anything on that list is a format decision for a later version, not a workaround for v1.

### 5.3 The Blender output (standard, followed faithfully)

The suite does not invent a Blender format. It emits what Blender itself documents:

- **Extension package (Blender 4.2 and later, including 5.x):** a folder (zipped for delivery) containing `__init__.py` and `blender_manifest.toml`. The manifest carries the name, id, version, tagline, maintainer, website, and the minimum Blender version. This is the primary output.
- **Legacy add-on (older Blender):** a single-file or package add-on with a `bl_info` dict (name, author, version, Blender version, location, description, category). Available as a fallback when the target Blender predates extensions. The suite targets Blender 5.3 first, the version on his PC (decision D2, §15).
- **Code shape:** operators (`bpy.types.Operator`, with `bl_idname`, `bl_label`, `bl_options` including `REGISTER` and `UNDO`), panels (`bpy.types.Panel`), and settings (`bpy.types.PropertyGroup` registered on the scene). Classes are listed in one tuple and registered/unregistered in matching `register()`/`unregister()` functions, in reverse order. No loose global state: settings live in property groups, so they survive file reloads and stay undo-safe.
- **Install:** the standard routes — Blender's Extensions preferences (drag the zip in), or the add-ons folder. The suite's pack window can place the zip where Blender looks, and says exactly where it put it.
- **Imports (v0.6).** Blender loads the add-on as a package, so the entry imports shared modules relatively (`from . import pick`). The flat import that works in a Reblend pack (`import pick`, §5.1) does not work in Blender — each target's entry file imports the shared code its own way, and the shared code itself stays target-free.

### 5.4 The shared project (what the suite authors)

A suite project is a folder of plain files on disk. Nothing hidden, nothing in a database:

```
projects/water-splash/
  project.json     Name, description, targets (reblend, blender, or both),
                   version, icon, author, contributions. One file,
                   human-readable.
  idea.md          The original plain-words idea, kept verbatim.
  plan.md          The plan the AI showed before building, as approved.
  chat.jsonl       The chat history for this project, one message per line.
  src/             The behavior code, organized per target where it differs:
    shared/        Target-free logic (math, randomization, presets).
    reblend/       Reblend-side code (addon.py + modules).
    blender/       Blender-side code (__init__.py + modules).
  assets/          Icons, test scenes, textures, presets.
  tests/           The project's checks: what "works" means, in plain words
                   plus the automated checks that prove it.
  renders/         Captured renders from test runs, newest first.
  packs/           Built packs (.rblpack zips, Blender zips) with version names.
```

**The emitter maps this layout into the pack (§5.1):** `src/reblend/addon.py` becomes the pack's `addon.py`; the modules from `src/reblend/` (everything but `addon.py`) and from `src/shared/` become the pack's `code/`; `assets/`, `README.md`, and `icon.png` copy from the project root. The project's working files — `project.json`, `idea.md`, `chat.jsonl`, `tests/`, `renders/`, `packs/` — never ship.

**Why plain files:** Joshua's other apps already work this way (Reblend scenes are JSON; the saved-materials library is `materials.json`). Plain files can be opened, grepped, copied, backed up, and fixed with ordinary tools. A database would add a failure mode and hide the work. The suite uses no database server anywhere.

**Versioning:** a project's version lives in `project.json` and flows into both emitters, so the Reblend pack and the Blender add-on for the same project always share a version number. Bumping the version is one action in the pack window, and the suite never bumps it silently.

---

## 6. The workstation: the windows

The Core Rule governs the whole workstation: proper menus and windows, proper navigation to dedicated workspaces where necessary, **no one-window crowded builds ever**. Every function gets its own closable window (U1). The menu bar is the map: everything is reachable from it, and every window can be closed and reopened without losing work.

There are eight windows. No window does another window's job.

### 6.1 Window map

```
Menu bar (always visible in every window)
  File    Project    Chat    View    Render    Test    Pack    Help
    |         |        |       |        |        |       |       |
    v         v        v       v        v        v       v       v
  +--------+ +-------+ +------+ +-----+ +------+ +-----+ +------+ +------+
  | Home   | | Chat  | | Code | | ... | |Reblend| |Test | | Pack | | How  |
  | (hub)  | | (AI)  | |      | |     | |Render | |Runs | |      | | to   |
  +--------+ +-------+ +------+ +-----+ +------+ +-----+ +------+ | Use  |
  | Library|                             |Blender|              +------+
  |        |                             | Test  |
  +--------+                             +-------+
```

Default sizes fit the 1366x768 screen (U5): the main windows open at 1100x680 or smaller, geometry remembered between runs (QSettings). Nothing opens maximized by default; nothing opens off-screen. Every window has a real menu bar (U38) and a status line at the bottom that says what is happening right now (U16).

### 6.2 Home (the hub)

The first window. A bento layout (technique 5 / entry 005): one hero card for the current project (its name, its target, its last test result, one **Open in Chat** button), small cards for recent projects, and a row of starters: **New add-on** (one box: what should it do?), templates (operator, panel, brush, material family, simulation — each a one-tap starting point with real working code, not a blank file), and the first-target shortcuts from §11. Empty state teaches instead of scolding (entry 031): no projects yet means a friendly "Start with an idea" card and the Surprise template one tap away. Nothing is selected by default (U6).

### 6.3 Chat (the AI workstation)

The front door and the heart of the suite. Prompt-first layout (entry 010): the text box sits at the center; the conversation is the work. Full design in §7. The chat window shows the current project's conversation, the plan when one is on the table, the list of proposed changes awaiting approval, and the working status (model name, what it is doing right now, elapsed time, cancel). Tool calls are shown as they happen — "reading addon.py", "rendering test scene", "running 6 checks" — never hidden behind a spinner.

### 6.4 Reblend render window

A live Reblend viewport inside the suite: the real Reblend engine, running in-process, showing a test scene with the current add-on loaded. Orbit, zoom, and select work the way they do in Reblend, because it *is* Reblend's viewport code (§8.2). The add-on's own controls appear in it exactly as they will appear in Reblend (wheel button, panel, brush). A **Reload add-on** button re-reads the pack without restarting anything. A before/after toggle compares the scene with and without the add-on. The window is labeled with the project name and the test scene name, so there is never doubt about what is on screen.

### 6.5 Blender test window

Shows Blender test results, not a live Blender window (§8.3 for why). After a test run: the rendered images, the plain-words checklist (loaded, registered, ran, unloaded, errors if any), the Blender log in plain words with the technical lines one click away, and a **Re-run** button. While a run is going, the window shows live progress (which step Blender is on, elapsed time, cancel). The renders are saved into the project's `renders/` folder, newest first, so a run can be compared with the last one.

### 6.6 Code window

For reading and fixing what the AI wrote. A file tree for the project (shared / reblend / blender / tests), a plain editor with line numbers and Python highlighting, and a diff view: every AI change is shown as before/after before it is approved, and the history of applied changes is browsable. Search across the project. No build tools, no terminal pane, no debugger: the suite is not a general editor, and the code window does not pretend to be one. Its job is *read it, fix a line, see the diff* — nothing more.

### 6.7 Test runs window

The project's checks, listed in plain words with a pass/fail light each: "Loads without errors", "Registers and unregisters cleanly", "Undo restores the scene", "Runs on the tavern scene without crashing", "Frame rate on this PC: measured". One **Run all** button. Each run is saved (date, result, renders, log) so regressions are visible: this run versus the last run, side by side. A failing check explains itself in plain words first ("The add-on crashed when the scene had no objects") with the technical traceback one click away, and a **Ask chat to fix it** button that carries the failure into the chat with full context.

### 6.8 Pack window

Where a project becomes a file. Shows the manifest as the suite will write it (name, version, targets, contributions, permissions — each field explained in plain words underneath it, U20), the icon, and the build buttons: **Build Reblend pack**, **Build Blender add-on**, **Install in Reblend**, **Install in Blender** (places the file and says where). The version bump is one explicit action. The pre-pack scan runs first and reports in plain words: secrets check, manifest check, contribution check, last test result. A pack is never built on a failing test run without Joshua saying so explicitly — the window says the tests are red and asks, it does not silently build anyway.

### 6.9 Library window

Every pack the suite has built, plus the templates and starters: cards with icon, name, version, target, last test result, and one-line description. Open a pack's project, reinstall a pack, or delete a pack (delete confirms, defaults to No, U23/U31). The library is a shelf, not a store: no ratings, no downloads, no network.

### 6.10 The supporting surfaces

- **Command palette (Ctrl+K, entry 043).** Every command in the suite, searchable by name, with its shortcut shown beside it so the palette teaches as it serves. Menus and buttons still exist for everything — the palette is a shortcut, never the only path.
- **How to Use index (U22).** A full index in the Help menu: every window, every action, in plain words, with the three journeys from §3 as the first three entries.
- **Status and measurements.** A slim status line in every window (what is happening, with a light) and a measurements strip in the chat and render windows: model speed, RAM in use, render frame rate, test progress — real numbers, live, display-only (U37). The backend adjusts; the user watches.
- **Toasts, not popups (entry 030).** Short confirmations ("Pack installed in Reblend") appear as a quiet toast and fade. Errors get a proper message with a fix, never a bare toast. Modal dialogs never stack (U18).

---

## 7. The AI chat interface

### 7.1 What the chat is

The chat is the way work gets done. It is not a chatbot pasted onto a tool; the tool *is* the chat plus the windows around it. The model is local (Ollama, on his PC, $0), chosen with guidance (U39: the suite shows what the model does and whether it fits this PC; the backend picks the size and settings for the machine). The chat window is prompt-first (entry 010): the text box is the center of the window, and everything else serves the conversation.

### 7.2 The loop: Plan, Approve, Build

Every job follows the same loop, and the loop is visible:

1. **Ask.** Joshua describes what he wants in plain words. The chat asks for the minimum up front (U21) — one question at a time, only when the answer changes the work.
2. **Plan.** The AI answers with a short plan: what it will build, which files it will touch, which target it is for, what the test will show. The plan is shown *before* anything is built, in plain words, with the file list attached. No plan, no build.
3. **Approve.** Joshua taps **Build it**, or edits the plan in chat first. Approval covers exactly the plan shown; if the AI discovers it needs something the plan did not cover, it stops and asks instead of expanding the job on its own.
4. **Build.** The AI works visibly: streaming text, tool calls named as they run, files listed as they change. Long work runs in worker threads; the UI never blocks (U30). Cancel is always available (U26).
5. **Show.** The result appears where it belongs: the render window for anything visual, the test window for checks, the code window's diff view for the changes. The chat summarizes what changed, in plain words, with the proof attached (a render, a test result), never a bare claim.
6. **Fix.** If it is wrong, Joshua says so in plain words and the loop runs again on the same project, surgically (U8). The previous version is kept, so any step can be undone.

### 7.3 What the chat can do (its tools)

The chat works through a fixed set of tools, each one visible when it runs:

| Tool | What it does | Needs approval? |
|---|---|---|
| Read files | Read project files, Reblend sources, and Blender API references the suite ships. | No — reading is free. |
| Propose changes | Write new code or edits as a *proposal* (diff shown in the code window). | The proposal itself is free; *applying* it needs his tap. |
| Apply changes | Apply an approved proposal to the project files. A snapshot is taken first, so it can be undone. | Yes — one tap per proposal, never blanket. |
| Render (Reblend) | Load the project into the render window on a test scene and capture the frame. | No. |
| Run tests | Run the project's checks (or all checks) and report. | No. |
| Drive Blender | Run Blender in background mode with a test script; bring back renders and logs. | No — but it says it is starting Blender first, and it can be cancelled. |
| Build pack | Assemble a `.rblpack` or Blender zip from the project. | Yes — packing is the pack window's job; chat can prepare it, Joshua taps Build. |
| Search | Search the project, the Reblend tree, and the suite's shipped API notes. | No. |

What the chat **cannot** do: install anything, delete anything, change Reblend itself, change the suite's own code, touch the network, or read files outside the project and its reference folders. Destructive actions confirm first and default to No (U23, U31). The chat never silently skips a step: if a file could not be read or a check could not run, it says so with the reason (U32).

### 7.4 Proposals, diffs, and undo

No AI-written code reaches the project files without Joshua's tap. The flow is fixed: the AI writes a proposal, the code window shows it as a before/after diff, the chat summarizes it in plain words ("adds the splash strength knob, changes 3 lines in addon.py"), and Joshua taps **Apply** or **Change it**. Before any apply, the suite snapshots the affected files; **Undo** restores them exactly. Chat history is kept per project (`chat.jsonl`), so a conversation can be resumed days later with full context, and the history shows what was proposed, what was applied, and what was undone.

### 7.5 Trust cues and provenance (entry 010)

Every AI message carries its grounding, quietly: which files it read, which tools it ran, which lines it changed. Generated code is marked as generated in the code window until Joshua edits it; his own edits are never re-labeled. Test results show the actual numbers (frame rate measured on this PC, checks passed out of total) instead of adjectives. The chat never says "done" without the proof attached — a render, a test run, or a diff. When the model is unsure, it says so and offers the two readings instead of picking one silently (entry 034, conversational repair).

### 7.6 Errors, the plain-words way

When something breaks — a Python error, a Blender failure, a test crash — the suite leads with the plain-words sentence ("The add-on crashed when the scene had no objects in it"), then the fix it suggests ("Add a check for an empty scene"), then the technical detail one click away. Empty states teach (entry 031): a project with no tests yet shows "No checks yet — the chat can write them" with one button, not a blank table. Nothing ever dead-ends: every error carries a next step (U29).

### 7.7 The models (decided, from his roster)

The chat runs on models already on his PC — the 11-model Forge roster from his `ollama list` screenshot (2026-11-12). No new downloads are needed to start. The suite uses Forge's proven seat pattern: a driver that plans and talks, a code seat that writes code, and a vision seat that looks at renders. Seats run one at a time — one model loaded at once, the backend swapping between them — so RAM stays inside 8 GB.

- **Driver: qwen3.5:4b.** The strongest generalist on his roster that fits. It plans, talks, runs the tools, and checks the results.
- **Code seat: qwen2.5-coder-abliterate:1.5b.** Writes code under the driver's plan. Code seat only, never the driver — it failed a driver trial on 2026-11-09, and the suite does not repeat that mistake.
- **Vision seat: qwen3-vl:2b-instruct.** Reads test renders ("is the splash visible? is the frame washed out?") so the loop can check visual results instead of trusting numbers alone. Slow and rough on CPU — the suite uses it for short looks, not long sessions.

The honest constraint stands: small local models write slower, buggier code than big ones, and the suite designs around it the same way — the test loop is the quality control, templates carry the boilerplate, steps stay small. The Phase 2 test proves it: the loop builds PO8 with these seats. If it cannot, the fallback is smaller steps and more template use — the suite degrades gracefully instead of failing. If a better-fitting model appears on his roster later, the backend picks it up; the seat pattern does not change.

---

## 8. Rendering and testing inside the program

This is the part Joshua asked for most directly — rendering windows, and testing the add-ons inside the program — so it gets the most honest treatment in the dossier, including what is *not* possible.

### 8.1 The principle

Seeing is the test. A render window is not a preview decoration; it is where the add-on proves itself. Every visual add-on gets a test scene, a render, and a before/after comparison. Every non-visual add-on (a bake tool, a file exporter) gets a run against a real scene with real output files to inspect. Nothing ships on a claim; everything ships on a capture.

### 8.2 The Reblend render window: live, in-process, real

The suite embeds Reblend's actual viewport. Not a copy, not a reimplementation, not a screenshot pipeline: the same `Viewport` (QOpenGLWidget) and the same `light_engine` modules Reblend itself runs, loaded in-process by the suite. The add-on under development is loaded into that viewport through the same loader Reblend will use (§5.1), so what Joshua sees in the suite is what the add-on will do in Reblend. There is no "works in the suite, breaks in Reblend" gap by construction — the render path is shared, not duplicated.

How it works, concretely:

- **Test scenes.** The suite ships a small set of test scenes with the project templates: the tavern tabletop (the Reblend reference scene), an empty scene, a single-object scene, a heavy scene (many objects, for frame-rate measurement). A project can add its own. Test scenes live in the project's `assets/` folder as plain scene JSON, so they can be opened in Reblend itself.
- **Live reload.** Editing the add-on (by chat or by hand in the code window) and tapping **Reload add-on** re-reads the pack and re-renders, without restarting the suite or the viewport. The scene stays where it was; the camera stays where it was (U28: actions preserve UI state).
- **Playground mode (entry 066).** The render window runs on a *copy* of the test scene. Nothing the add-on does in the render window touches the real project files or the real test scene until Joshua says so. A **Reset scene** button restores the test scene in one tap. The window is labeled with the project and scene names, and the playground copy is labeled as a copy, so play is never mistaken for work.
- **Before and after.** A toggle shows the scene with the add-on disabled versus enabled, from the same camera. For material and simulation add-ons this is the proof: the same frame, both ways.
- **Capture.** Any frame can be captured to the project's `renders/` folder with one button, and every test run captures its frames automatically. Captures are plain PNGs, dated, comparable across runs.
- **Measurements.** Frame rate, frame time, and triangle count are shown live under the viewport (U37) — real numbers from the embedded engine, labeled as this PC's numbers.

**Dependency (flagged, not hidden):** the embedded viewport needs Reblend's `light_engine` as an importable package, and the pack loader (§5.1) must exist before any add-on can load into it. Both are Phase 1 work (§12), the loader in the REBLEND DEV thread. Until the loader exists, the render window can show scenes but cannot load packs — the dossier does not pretend otherwise.

### 8.3 The Blender test window: driven, not embedded

Blender is a full program with its own window, its own event loop, and its own Python. It cannot be embedded inside another program's window the way Reblend's viewport can. Any dossier that promised a "live Blender viewport inside the suite" would be promising something that does not work. So the suite drives Blender instead of embedding it — the same way SKULLPT already does.

- **Blender is on his PC: 5.3.0, on his Desktop, working** (confirmed 2026-11-13). The suite finds it the way SKULLPT does: the `~/.local/bin/blender` symlink first, then the standard locations. No download, no install step, no guessing.
- **How a run works.** The suite writes a small test script, starts Blender in background mode (`blender --background --factory-startup --python test_script.py`) as a subprocess — SKULLPT's exact shape, proven in `blender_export.py` — and Blender loads the add-on, runs the test steps against a test scene (a `.blend` file shipped with the project templates), renders the requested frames, and writes out images and a result file. The suite reads the results back and shows them in the Blender test window: the renders, the plain-words checklist, and the log. A timeout is a result, not an explosion: the run reports what finished and what did not, in plain words.
- **What Joshua sees.** The renders, the checklist, and the plain-words summary — the same shape as the Reblend results, so the two targets feel like one workflow. What he does *not* see is a live Blender window to orbit in. If he wants to poke at the add-on by hand in Blender, the pack window installs it into Blender and he opens Blender himself. The suite is honest about that boundary in the window itself ("Blender runs in the background for this test — open Blender to try it by hand").
- **What the suite needs.** Nothing new: Blender 5.3.0 is already there, and the suite targets it — the extensions format (`blender_manifest.toml`) is the primary output, with the legacy `bl_info` form as the fallback for older versions. If Blender is ever missing (a fresh machine, a moved folder), the Blender windows say so plainly ("Blender is not installed — Blender tests need it") and the Reblend side works fully. The suite never downloads or bundles Blender.
- **Cost on his PC.** Blender in background mode is heavy: it loads its full application to run a test. The suite runs one Blender job at a time, in a worker thread, with progress and cancel (U25, U26, U30), and never starts Blender while a Reblend render is mid-test. The measurements strip shows Blender's elapsed time honestly, so a slow test reads as slow instead of looking stuck.

### 8.4 The test harness: checks in plain words

Every project carries its checks in `tests/`. The suite ships a standard set that runs for every project, and the chat writes project-specific checks from the plan (a water add-on gets "a wooden crate floats, a steel ball sinks"; a bake add-on gets "three PNGs at the chosen size, no partial files on cancel").

**The standard checks (every project, both targets where they apply):**

1. Loads without errors.
2. Registers cleanly, and unregisters cleanly (everything registered is unregistered, in reverse).
3. Does not crash on the empty scene.
4. Does not crash on the tavern scene (Reblend) / the template scene (Blender).
5. Undo restores the scene exactly (one action, one undo step).
6. Uninstall leaves nothing behind (no files, no settings, no menu entries).
7. Pack scan: manifest valid, contributions declared, no secrets, icon present.
8. Performance: frame rate (or run time for non-visual add-ons) measured on this PC and recorded — never judged against a threshold the suite invented. The number is reported; Joshua decides if it is good enough.

**How results are reported:** a checklist, one line per check, plain words, pass/fail light, with the proof attached (render, log line, output file). A failing check carries the failure into the chat with one button ("Ask chat to fix it"), with the full context attached. Runs are saved and comparable: this run versus the last run, so a fix that breaks something else is visible immediately.

### 8.5 What testing does not cover

The suite tests the add-on; it does not test Reblend or Blender. If Reblend itself has a bug, the suite's checks will show the add-on failing in a way that points at the engine, and the chat says so ("this looks like a Reblend problem, not a pack problem") instead of rewriting the pack to work around it. Engine bugs go to their own threads. The suite also does not test on any machine but his: all numbers are this PC's numbers, labeled as such.

---

## 9. Full-stack architecture

### 9.1 Stack (chosen, with reasons)

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3 | Reblend is Python; Blender add-ons are Python; Joshua's whole workshop is Python. One language for the suite, the packs, and the tests. |
| UI toolkit | PySide6 (Qt) | Native Linux desktop windows (U2), the same toolkit as Reblend, Code Forge, and every other BNB app. Shared knowledge, shared patterns, shared fixes. |
| 3D | Reblend's `light_engine` (in-process) + Blender subprocess | The Reblend viewport is real, not a copy (§8.2). Blender is driven, not embedded (§8.3). |
| AI | Ollama, local models — qwen3.5:4b driver, qwen2.5-coder code seat, qwen3-vl:2b vision seat (§7.7) | $0, offline, no account, no secrets leaving the PC. The models run on his machine; the chat never calls a cloud API. |
| Storage | Plain files (JSON, JSONL, Markdown, PNG) | Inspectable, greppable, copyable, survivable. No database server, no sync service (§5.4). |
| Packaging | Zip (`.rblpack`, Blender extension zip) | Both targets ship as zips. The suite builds them with the standard library. |
| Tests | Python `unittest` + Qt drives under Xvfb | The same harness shape as Reblend's suite, proven on this VM and on his PC. |
| Installer | GUI double-click installer + `.desktop` + icon (U3, D2, D3) | The same delivery shape as every BNB release. No terminal to install or run. |
| Cost | $0, every layer | No paid dependency anywhere in the stack. |

The install writes two menu entries: the app itself and an Uninstall entry (the `devsuite-uninstall` console script, same baked-path pattern, no icon yet — the icon is designed with Joshua). The Uninstall entry opens the uninstall window on its own, with no installer window behind it, so the suite can be removed from the menu even after the release tree is deleted. The installer package ships inside the installed distribution for that reason.

What is **not** in the stack: no web server, no web UI, no cloud API, no database server, no telemetry, no account system, no container, no build farm. The suite is a desktop program that runs on one PC.

### 9.2 Layers

```
  +--------------------  WINDOWS (Qt, one function each)  -------------------+
  | Home | Chat | Reblend Render | Blender Test | Code | Test Runs | Pack | Library |
  +------------------------------  SERVICES  --------------------------------+
  | Chat service  | Project service | Render service | Test service | Pack service |
  | (plan/build,  | (projects,      | (Reblend live, | (checks,     | (manifest,  |
  |  tools, undo) |  snapshots)     |  Blender drive)|  runs)       |  emitters)  |
  +------------------------------  ENGINES  ---------------------------------+
  | Ollama (local model) | Reblend light_engine (in-process) | Blender (subprocess) |
  +------------------------------  DISK  ------------------------------------+
  | ~/DevSuite/projects/ | ~/DevSuite/library/ | ~/.config/DevSuite/ | Reblend packs folder |
  +--------------------------------------------------------------------------+
```

- **Windows** show things and take input. They hold no business logic beyond their own display. A window can be closed and reopened without losing work, because the state lives in the services and on disk.
- **Services** do the work. Each service owns one job (chat, projects, render, test, pack) and talks to the others through plain function calls, not messages or queues. No service reaches into another's internals.
- **Engines** are the heavy lifters: the local model, the embedded Reblend engine, the Blender subprocess. All engine work runs in worker threads; the UI thread never waits on an engine (U30).
- **Disk** is plain files (§5.4). Settings live in QSettings (window geometry, last project, model pick) and in one JSON settings file for the rest. Logs live in the rotating debug log layer (U12).

### 9.3 Module layout (proposed tree)

```
devsuite/
  main.py                 Entry point. Single instance (U27). Applies the stylesheet.
  devsuite/
    __init__.py
    app.py                Application setup, menu bar, window registry.
    style.py              The design system (one file, semantic tokens, §10).
    settings.py           QSettings + settings.json. Backend self-config (U35).
    logging_layer.py      Debug log layer: rotating logs, ring buffer, report (U12).
    projects/
      model.py            Project: load/save project.json, snapshots, undo.
      templates.py        Starter templates (operator, panel, brush, material, sim).
      library.py          The library shelf: built packs, reinstall, delete.
    chat/
      engine.py           Chat loop: plan, approve, build. Tool dispatch.
      tools.py            The tool set (§7.3). Each tool named, logged, visible.
      ollama.py           Local model client. Guided model pick (U39).
      history.py          chat.jsonl read/write per project.
      prompts.py          System prompts: plain instructions, no metadata filler.
    render/
      reblend_view.py     The embedded Reblend viewport + live reload + capture.
      blender_drive.py    Blender subprocess runner: script, run, collect results.
      scenes.py           Test scenes: load, playground copies, reset.
    testing/
      checks.py           The standard checks (§8.4) + project checks.
      runner.py           Runs checks, saves runs, compares with the last run.
    packing/
      manifest.py         Manifest read/write/validate for both targets.
      reblend_emit.py     The Reblend emitter: project -> .rblpack.
      blender_emit.py     The Blender emitter: project -> extension zip / legacy.
      secrets_scan.py     Pre-pack secret scan. Refuses, naming the file.
      install.py          Install into Reblend / Blender folders. Reports where.
    ui/
      home.py chat_win.py code_win.py test_win.py pack_win.py library_win.py
      render_win.py blender_win.py palette.py help_index.py widgets.py
  tests/                  unittest suite + Qt drives + verify scripts.
  install.sh run.sh       GUI installer + launcher (bash, never sh — AGENTS.md).
  icon.png                Creative, beautiful icon (D3). Designed with Joshua.
```

### 9.4 Data model

- **Project** (`project.json`): id, name, description, targets, version, author, icon, created date, contributions (v0.7 — the §5.1 contributions dict, owned by the pack window; `{}` when nothing is declared yet). One file, human-readable.
- **Chat** (`chat.jsonl`): one JSON object per line — role, text, tool calls, proposals, approvals, timestamps. Append-only; undo lives in the snapshots, not in the history.
- **Snapshot**: a dated copy of the files a proposal touches, taken before apply. Undo restores from the snapshot. Snapshots are plain file copies in the project folder, pruned only when Joshua says so (no silent cleanup).
- **Test run**: a dated folder — `result.json` (checks, pass/fail, numbers), renders, log excerpt. Comparable across runs.
- **Pack**: the built zip, plus a `build.json` beside it recording the project version, the target, the test run it was built from, and the date. A pack always traces back to the run that proved it.
- **Shelf** (v0.8, `shelf.json` in the app data folder): the library's record of every pack the suite has built — one entry per built file (pack path, project id/name/root, version, target, built date, test run id or null, description). A record, not the packs themselves: rebuilding updates the entry, deleting removes it, and a damaged shelf reads as empty rather than crashing anything.
- **Settings**: window geometry and last project in QSettings; model pick, Blender path, Reblend path, and the backend's measured machine profile in `settings.json`. Nothing sensitive is ever stored (no keys, no tokens — there are none to store).

### 9.5 Backend self-config (U35, U36) and measurements (U37)

On first run and quietly ongoing, the backend measures the machine — RAM, CPU count, disk space, whether Ollama is running, which models are installed, whether Blender is installed, where Reblend lives — and sets the working values under the hood: which model size to use, how many jobs run at once (2 on his PC, U25), render quality for test scenes, Blender timeout behavior. The user never sees a settings form for any of this (U36: settings that don't change don't appear). What the user *does* see is the measurements strip: live numbers, fun like science software (U37) — model tokens per second, RAM in use, frame rate, test progress. Display, not controls. The backend adjusts; the user watches.

### 9.6 Threading, safety, and the debug layer

- Long work runs in worker threads; the UI never blocks (U30). Every long operation shows progress and offers cancel (U26). Heavy background work leaves the desktop usable (U25).
- Packs under test run in a worker-owned Reblend viewport session; a crashing pack is caught, reported in plain words, and disabled — it never takes the suite down with it. (The in-process limit is honest: a pack runs in the suite's process while testing, like a Blender add-on runs in Blender's process. The test harness isolates *results*, not memory. A truly hostile pack is out of scope: packs are Joshua's own code.)
- The debug log layer (U12) is in every build: rotating timestamped logs, a last-200 ring buffer, traceback capture, a scrubbed report, and a Debug report button in the Help menu.
- Single instance (U27): re-clicking the icon focuses the running suite. Modal dialogs never stack (U18). Actions preserve UI state (U28). Destructive confirmations default to No (U23, U31). Bad input gets a friendly plain error, never a dead end (U29). Nothing is silently skipped (U32).

### 9.7 The update check (standing order, 2026-11-17)

On launch, the app silently checks its GitHub repo for a newer Release — a plain GET to the public releases endpoint, no token, no identifying information. Up to date, unreachable, or no repo yet is silence: no popup, no noise. A newer release asks first — a popup, and only Joshua's tap pulls anything. The pull goes through the verified path: the release carries the release tree as a zip plus a `.sha256` sidecar, and the zip's SHA-256 must match the sidecar before anything installs; a mismatch refuses in plain words and installs nothing. GitHub's own source zipball is never used — it has no checksum sidecar, so it cannot go through the verified path. The install runs the extracted tree's own installer in a subprocess (the installed suite ships the installer package too, for the Uninstall menu entry — the update still runs the verified tree's copy, because the new version's installer may differ from the installed one), reusing the existing venv. Once installed, the program asks whether to restart now or on the next launch: Yes relaunches the installed console script and quits; No waits — the new files are in place and the next launch runs the new version. A manual "Check for updates" in the Help menu reports its result in plain words, whatever it is. A tree run with no install has nothing to update, so it skips the launch check entirely and the manual check says so. No setting or toggle in v1 (U35/U36): the order says the check runs on launch, silently. The repo is REBLEND-ADDON-DEV-SUIT (D8 — Joshua's spelling; he created it 2026-11-18, the first push landed the same day, and the first release, v0.1.0, carries both assets). The check was run against that real release the same day: at 0.1.0 it reports current; from 0.0.9 it reports newer and resolves both asset URLs. The release process must produce both assets — the tree zip with `pyproject.toml` at its root, and the sidecar in `sha256sum` form.

---

## 10. Design system (from the attachments)

The three uploads are the source material for this section, reconciled to the current rules where the uploads are stale (§0, Sources). The philosophy is Part 1: complex underneath, simple on top; the backend does the confusing work; the machine configures itself; fun like science software; real menus.

### 10.1 The techniques picked for this app

The techniques file says: do **not** use all twelve in one app — pick two or three that fit what the app actually does. The suite picks three primaries and a supporting set, each with a reason tied to the job.

**Primaries:**

1. **AI-native patterns (technique 10 / entry 010).** The suite *is* an AI product: streaming text as the model works, a prompt-first layout with the text box at the center, trust cues (which files were read, which tools ran, what changed), and provenance (generated code marked until Joshua edits it). This is the technique the whole chat window is built from.
2. **Calm technology (technique 3 / entry 003).** The suite does long, heavy work — model runs, renders, Blender drives. The interface stays quiet while it works: a light plus a status line, a progress chip, a toast when something finishes. No modals for status, no popups for progress. The app is a good roommate, not a demanding houseguest.
3. **Progressive disclosure (technique 12 / entry 012).** A screen with three choices is a toy; a screen with thirty is a cockpit. New add-on asks one thing. The manifest shows the fields that matter and tucks the rest one tap away. The Blender log shows the plain-words summary first, the technical lines on demand. The power is all there; the screen never shows it all at once.

**Supporting (each earns its place in one window, not everywhere):**

- **Micro-interactions (1 / 001):** button press dips, the finish checkmark, the send feedback — 100–150 ms, transform and opacity only. The finish moment matters most: a small celebration when a pack builds or a test run goes green.
- **Just-in-time GUI (4 / 004):** approval controls appear when a proposal is on the table and vanish when it is not; Blender controls appear only when Blender is installed; the reload button appears only when the render window has an add-on loaded. Zero inventory.
- **Bento grids (5 / 005):** the Home window only. One hero card, small cards around it, size as hierarchy.
- **Delight, done right (8 / 008):** personality in the small places — the empty state that teaches, the error that helps, the quiet celebration when a pack installs. Not in the main workflow.
- **Shape morphing (9 / 009):** a project card expands into the chat window; a check expands into its detail. Fast (under 400 ms), interruptible.
- **Skeleton screens and honest loading (11 / 011):** lists that load (library, test runs, chat history) show their shape immediately with real numbers, never a dead screen or a fake progress bar.
- **Playground mode (entry 066):** the render window runs on copies with a one-tap reset, labeled as a playground so play is never mistaken for work.
- **Command palette (entry 043):** Ctrl+K, every command searchable, shortcuts shown so the palette teaches.
- **Tooltips that teach (entry 040):** every field explains itself in plain words (U20); the longer explanation lives in the tooltip, not in a paragraph that doubles every row's height.
- **Empty and error states (entry 031) and conversational repair (entry 034):** §7.6 — errors lead with plain words and a next step; the chat repairs misunderstandings instead of failing.
- **See it before you commit (entry 017):** the diff view before any apply; the render before any pack; the before/after toggle in the render window. Nothing is committed blind.

**Deliberately not used:** Liquid Glass full-screen (fog on weak hardware, and glass everywhere costs frames — restraint only, if at all, on small floating surfaces); spring physics as a default (earned only on grabbed content, and this workstation is mostly typing and clicking, not dragging); neo-skeuomorphic knobs (the suite has few continuous controls — the add-ons it *builds* may have them, the suite itself does not need them); dockable panels (entry 063) — the suite uses separate windows per U1, not docks. The Reblend plan's docks belong to Reblend, not to this program.

### 10.2 Motion budget (from the techniques file)

- Micro feedback (press, hover): 100–150 ms. Small actions: 150–250 ms. Context changes (a window opening, a view switching): 250–400 ms.
- Ease-out for things entering, ease-in for things leaving, ease-in-out for loops.
- Animate transform and opacity only, never layout properties. In Qt: `QPropertyAnimation` with `OutBack` for overshoot where earned, plain easing elsewhere.
- Button press: scale to 0.97 over 150 ms. Card hover: lift 4 px over 200 ms, ease-out.
- Functional animation stays under 300 ms. Respect reduced-motion settings (entry 041).
- Idle animations stop at rest and restart on wake (the Forge GUIFX rule, adopted here).

### 10.3 Identity: pro software with its own material (U15)

The suite is a workshop, not a game and not a generic SaaS dashboard. Its identity is **the workbench**: dark, warm, solid surfaces; real menus; tools laid out like tools. It must not look like Code Forge — Forge's Future 3 Dark Glass Minimal with its ember accent is locked to Forge — and it must not look like every other app in the workshop. The dossier recommends a distinct accent in the green family (a bench lamp, a go-light: the color of "it works"), with warm paper-white text on charcoal surfaces, and one scarce accent used only for primary actions, focus, and the brand mark. The accent is decided (D4, §15): bench-green. The icon itself is designed with Joshua at build time (D3: creative and beautiful, not a placeholder).

Typography and layout follow the rules that already exist: one system (one button pair, one card style, one radius scale), semantic tokens in `style.py` (never raw hex in components), mono uppercase micro-labels for section headers ("mono is taxonomy, not body"), whitespace that groups instead of boxes, and density as a deliberate choice — rhythm tiers by hierarchy level, not undifferentiated density.

### 10.4 The filter (with the corrected Q4)

Every technique, window, and control in this dossier passes the four questions. Q4 is the corrected version — the uploads carry the struck line, and the dossier does not use it:

1. **Does it make it simpler?** If the user still has to think harder, it fails.
2. **Does it survive the toy test?** A child should be able to pick it up and use it.
3. **Does it run on his PC?** 8 GB RAM, no GPU, spinning hard drive. Cheap motion only, small surfaces for expensive effects, worker threads for heavy work.
4. **Does it make the app feel like itself?** Creativity is wanted. Decoration that gives the suite its workbench identity is fine. What fails is motion or styling that fights readability or costs frames.

### 10.5 Rule compliance (U1–U39, D1–D3)

| Rule | Where the dossier honors it |
|---|---|
| U1 One function, one window | §6: eight windows, each one job, all closable and reopenable from the menu. |
| U2 Native Linux desktop | §9.1: PySide6 Qt windows. No web UI anywhere in the suite. |
| U3 Double-click install and launch | §9.1, §12: GUI installer + app icon + menu entry in every release. No terminal. |
| U4 Launcher resolves | Installer bakes the app dir in at install (the `%k` pattern is not used). |
| U5 Fit his screen | §6.1: windows 1100x680 or smaller on 1366x768; geometry remembered (QSettings). |
| U6 Select nothing by default | §6.2, §7.2: no default project, target, model, or template selection anywhere. |
| U7 Default is no limit | §2: no caps invented anywhere in the dossier; defaults are measured and changeable. |
| U8 Surgical edits only | §7.2–7.4: the AI edits surgically; proposals are diffs; nothing extra is touched. |
| U9 Copy is his words or plain facts | All UI copy in this dossier is plain facts. No ad language, no coined slogans. |
| U10 No third-party brands in docs | This dossier names only the subjects (Reblend, Blender) and ordinary infra (Python, Ollama, Linux Mint). |
| U11 Labels use "and", never "&" | A build-time guard test, carried from MIMIK. |
| U12 Debug log layer | §9.6: rotating logs, ring buffer, traceback capture, Debug report button. |
| U13 Verify like the user | §13: fresh-clone verification, his real-PC verdict closes each phase. |
| U14 Web artifacts phone-first | Not applicable — no web UI. (The dossier PDF itself is phone-readable.) |
| U15 Pro software, real identity | §10.3: the workbench identity, distinct from Forge and from generic SaaS. |
| U16 Always show what it is doing | §6.10, §7.2: status light + text in every window; tool calls shown as they run. |
| U17 Copy tells the truth about limits | §8.3: the Blender boundary is stated in the window; §7.7: model limits stated honestly. |
| U18 Modals never stack | §9.6: one modal in flight; others queue with an honest message. |
| U19 Teenager-or-grandparent bar | §1: sharpened by U34 to the toy bar; the five-minute story (§3.1) is the test. |
| U20 Every field explains itself | §6.8 and throughout: plain-words line under every field. |
| U21 Minimum up front | §3.1, §6.2: one box to start; one question at a time in chat. |
| U22 How to Use index | §6.10: full index in the Help menu, journeys first. |
| U23 Destructive defaults to No | §6.9, §7.3, §9.6: delete and destructive confirms default to No. |
| U24 Long installs resumable | Applies to the suite's own installer and to model pulls (Ollama resumes). |
| U25 Heavy work leaves desktop usable | §9.5–9.6: 2 jobs max on his PC; one Blender job at a time. |
| U26 Progress and cancel | §7.2, §8.3: every long operation shows progress and offers cancel. |
| U27 Single instance | §9.3, §9.6: re-clicking focuses the running app. |
| U28 Actions preserve UI state | §8.2: reload keeps scene and camera; §9.6: scroll, focus, and place survive actions. |
| U29 Friendly plain errors | §7.6: plain-words errors with a next step, never a dead end. |
| U30 Worker threads, UI never blocks | §9.2, §9.6: all engine work in worker threads. |
| U31 Confirm destructive, clean escape | §7.3, §9.6: confirm first; Esc or tap-outside leaves things untouched. |
| U32 Never silently skip | §7.3: unread files and unrun checks are listed with reasons. |
| U33 No em-dashes in visible UI text | Build-time guard test. (This dossier document may use them; the app's UI may not.) |
| U34 Toy rule | §1, §3.1: the bar for every window. |
| U35 Backend configures itself | §9.5: machine measurement, silent and ongoing. |
| U36 Settings that don't change don't appear | §9.5: no settings forms for backend-chosen values. |
| U37 Real measurements, science software | §6.10, §8.2: live numbers, display-only. |
| U38 Real Windows-style menus | §6.1: proper menu bar, drop-down menus, collapsible headers. |
| U39 Guided model and size choices | §7.1, §9.5: what the model does + whether it fits; backend picks the size. |
| D1 Ship is GitHub-only | §12: push + Release. No zips in chat, no zip emails. |
| D2 Release carries icon + installer | §9.1, §12: every Release. |
| D3 Installer + beautiful icon | §9.1, §10.3: installer updates all dependencies; icon designed with Joshua. |

Plus the standing rules that are not U-numbers: **hard $0** (§9.1); **no secrets in code** (§5.1, §9.4); **no caps or rules without asking** (§2); **his real-PC verdict closes an item** (§13); **real function only** — every window, tool, and check in this dossier does something real, and anything that would not has been left out.

---

## 11. First targets (plan §9)

The suite's first targets are the add-ons plan §9 separated out of Reblend's base. They are also the suite's proving ground: each one exercises a different part of the workstation, in an order that builds confidence.

| # | Target | What it is | What it proves about the suite | Notes |
|---|---|---|---|---|
| 1 | **PO8 Surprise** | Seeded randomize: one button morphs the selected object into a fresh material (random family/style/layout + parameters), one undo step. Small. | The whole loop end to end on the smallest possible add-on: chat → wheel button → render → test → pack. Also the model-quality test (§7.7): if the loop can build PO8, it can build the rest. | Wheel bottom-row contribution. Deterministic: same seed, same material. |
| 2 | **PO11 Bake PBR packs** | Bake a procedural material to PNG maps (base colour, roughness, height) at 256/512/1024, with progress and cancel. Large. | A non-visual add-on: file output instead of a render, an offscreen bake instead of a viewport frame, cancel leaving no partial files. Tests the pack window's file handling and the test harness's output checks. | Resolution picker: the suite offers the sizes, the user picks — no default selected (U6). |
| 3 | **T26 Water** | Water surface (vertex waves + normal perturbation) + water particle presets (splash, drips, pour) + buoyancy and drag in water volumes. Large. | A simulation add-on: per-frame step function, a test scene with a floating crate and a sinking ball, frame-rate measurement that matters. The five-minute story (§3.1) is this add-on. | Needs T25 (transparency pass) in Reblend's base first — a REBLEND DEV dependency, flagged in §12. |
| 4 | **T27 SPH splash** | Small SPH fluid sim, bake-only. | Advanced simulation through the suite. | **Needs Joshua's separate approval** (standing order). Not authorized by this dossier. Listed so the direction is not lost. |
| 5 | **Anatomy + hair + sandbox (T32–T42)** | Anatomy presets, hair physics, sandboxes. Design delivered 2026-11-12. | A multi-part add-on family: presets + physics + scenes, testing the suite's ability to hold a big project across many sessions. | **Awaiting Joshua's approval + 6 decisions** from the design. Not authorized by this dossier. |
| 6 | **Image-to-character pipeline (T51–T63)** | Turn a photo into a character. Design delivered 2026-11-12. | The suite's hardest target: a pipeline, not a single tool. Proves the chat can hold a multi-step design. | **Awaiting Joshua's approval + 7 decisions** from the design. Not authorized by this dossier. |

**The Blender-side first target is decided (D3, §15): the Blender Surprise operator** — one button that randomizes the selected object's material for inspiration, the Blender mirror of PO8. Smallest possible loop, so the Blender emitter, the Blender drive, and the Blender test window are all proven on the smallest possible job before anything bigger is attempted.

**Order of proof:** PO8 first (smallest loop), PO11 second (files, not renders), T26 third (simulation). The rest wait on their own approvals. Nothing in this list is authorized to build by this dossier alone — the dossier is the plan; each target still starts when Joshua says so.

---

## 12. Build phases (on paper — no dates, no code yet)

Each phase follows the standing cycle: build → verify → push → Release → next phase. A phase is done when its done-when is met and Joshua gives his real-PC verdict. No phase starts until the previous one is verified. No dates are promised anywhere — the order is the commitment, not the calendar.

**Phase 0 — Dossier sign-off (this document).**
v0.1 asked the decisions; v0.2 answers them from evidence (§15). Joshua reads this dossier and corrects it; the dossier is revised to match his corrections. Done when: he says the plan is right.

**Phase 1 — Pack format lock + Reblend loader (dependency).**
The format in §5.1 is frozen as v1. The Reblend loader — the code in Reblend that reads `.rblpack` files, checks manifests, calls `register(api)`/`unregister(api)`, and renders declared contributions — is built in the REBLEND DEV thread, against this dossier's §5 as its spec. The suite's side of Phase 1 is the manifest writer/validator and the secrets scan, so the format can be tested from both ends. Done when: a hand-written test pack loads in Reblend, shows its wheel button, unloads cleanly, and a malformed pack is reported in plain words instead of crashing anything. *This phase gates all Reblend testing in the suite; it cannot be skipped or reordered.*

**Phase 2 — Chat + project core.**
Home window, chat window, code window (read + diff + apply), project model, snapshots and undo, Ollama client with the guided model pick, the tool set (§7.3), and the first template (operator). The model-quality test (§7.7) runs here: can the loop build PO8 with the model that fits this PC? Done when: Joshua can describe PO8 in chat, approve the plan, watch it build, read the diff, apply it, and undo it — all without a render window yet.

**Phase 3 — Reblend render + test.**
The embedded viewport (§8.2), live reload, playground copies, before/after, capture; the test runs window with the standard checks (§8.4); the test scenes. Done when: PO8 renders live in the suite, the checks run green on the tavern scene and the empty scene, and a deliberately broken pack fails with a plain-words explanation and a working "Ask chat to fix it" button.

**Phase 4 — Pack builder + Blender emitter.**
The pack window (§6.8), the Reblend emitter (project → `.rblpack`), the Blender emitter (project → extension zip, plus legacy fallback), the manifest UI, install-into-Reblend, install-into-Blender (file placement). Done when: PO8 packs for Reblend and installs from the suite; the Blender equivalent packs as a standard extension that installs in Blender by hand.

**Phase 5 — Blender drive + test-back.**
The Blender test window (§8.3): subprocess runner, test script generation, render and log collection, plain-words checklist. Done when: the Blender PO8-equivalent runs through Blender in background mode and its renders and checklist come back into the suite, with a failure case proven too (a broken add-on reports plainly, with its Blender log one click away).

**Build-sequence note (v0.4, 2026-11-17).** The Reblend emitter — manifest writer, zip builder, installer (Phase 4's Reblend half) — is built before Phase 3, because Phase 3's render and test work waits on the Reblend loader (Phase 1, REBLEND DEV thread) and the emitter is independently verifiable. The manifest writer also completes Phase 1's suite side, which this section defines as "manifest writer/validator and the secrets scan". The phase order itself is unchanged; only the build sequence moves while the loader is pending. (The emitter was briefly mislabelled "Phase 3a" in working notes; the label was corrected the same day.)

**No-terminal standing rule (v0.12, 2026-11-18).** Joshua never uses the terminal — not to build, install, run, or check anything — unless the work absolutely requires it and there is no click/GUI alternative, or a specific project explicitly says otherwise. This extends the installer rule (every program has a double-click installer launcher) from install/run to building. The terminal stays dev/VM-only for the assistant. Consequence for this suite: it is the tool that lets him build add-ons by clicking, so every flow he touches — building, packing, installing, updating, uninstalling — must work from its windows, and no step may hand him a terminal command as the way to do it. Shell scripts (install.sh, uninstall.sh, run.sh) and terminal fallbacks in error messages exist for the assistant and the sandbox, never as his path.

**Phase 6 — Library, polish, release.**
Library window, command palette, How to Use index, measurements strip, the icon (designed with Joshua), the GUI installer, the full test suite green, fresh-clone verification (§13). Done when: the suite installs by double-click on his PC, opens, builds PO8 end to end, and Joshua's verdict closes it.

**After v1 (not phases, just direction):** T26 water through the suite (§11); the Blender-side catalog growing past the first operator; format v1.1 additions only as real packs demand them, each versioned, each with his say-so. Nothing after v1 is scheduled or promised by this dossier.

### Dependencies, stated plainly

- **Reblend loader (Phase 1)** gates Reblend render and Reblend pack testing. Owned by the REBLEND DEV thread. The suite cannot test Reblend packs until it exists.
- **T25 transparency pass** (Reblend base) gates T26 water. Owned by the REBLEND DEV thread.
- **Ollama + the roster on his PC** gates the chat. The models are already there (his 11-model roster); the suite detects what is installed and says plainly what is missing.
- **Blender 5.3.0 on his PC** — resolved, not a risk: it is on his Desktop and working, found via the symlink. Blender testing needs nothing new.
- **Joshua's decisions (§15)** — answered in v0.2. Nothing in the plan waits on a decision anymore; a changed answer is a dossier edit.

---

## 13. Verification plan

**The rule:** verify like the user (U13). The suite is verified the way Joshua will actually use it — on his 8 GB Mint PC, by double-click, with real projects — and his real-PC verdict closes each phase. No phase is called done on a sandbox result alone.

**The suite's own tests (run every phase):**

- Unit tests for the format (manifest validate, emitter output, secrets scan, snapshots, undo), the chat tools, and the test harness — plain `unittest`, no Qt needed.
- Qt drives under Xvfb for every window: open, use, close; the chat loop with a scripted model; the render window with the embedded viewport; the pack window end to end. Drives use the real widgets, not mocks of them.
- The guard tests: no `&` in visible labels (U11), no em-dashes in visible UI text (U33), no blue where the identity forbids it (once the identity is locked in D4), no secrets in the tree.
- Fresh-clone verification: the release is verified from a fresh clone of the repo, not just from the build tree — the MIMIK lesson.
- Installer test: double-click install in a clean home, app-menu launch, uninstall leaves nothing behind.

**The proving builds (the real verification):** PO8 end to end in Phase 3 (chat to installed pack, on his PC, by his hands); PO11 in Phase 4; T26 after v1. A phase whose proving build fails on his PC is not done, whatever the suite says.

**What is never claimed:** sandbox frame rates are labeled llvmpipe, never presented as his-PC numbers. A green test run is reported as a green test run, not as "it works" — the render and his eyes are the proof. Merged is not shipped; shipped is a GitHub Release with the installer and the icon (D1–D3).

**Verification round, 2026-11-17 (Phase 6, sandbox):** the guard tests now exist (`tests/test_guards.py`, stdlib-only, run on both interpreters): no secrets in the shipped source (the suite's own scanner over `devsuite/`, `installer/`, the shell scripts, the `.desktop` launcher, `pyproject.toml`, and this dossier), no blue in the workbench identity (every color literal in `devsuite/ui/`), and no em-dash or bare `&` in visible text (every string literal in the shipped Python, docstrings excluded — backend error strings are in scope because the windows show them verbatim). The round proved and fixed three defects in place: the secrets scanner refused clean code (`token = self._build_token`, prose "the test it must pass:") — it now exempts code values and bare "pass" only counts with "="; 28 user-visible strings carried em-dashes (chat, pack, library, and installer messages) — all reworded, with two named non-visible exemptions (the planner system prompt, the generated Blender test script); installer error messages ran two sentences together when the quoted detail had no period. Fresh-tree verification (no repo yet, so a clean copy, not a clone): both suites green in the build tree and in the fresh copy with identical counts — 404 tests (Qt venv, 3 skipped) and 327 (system python, 10 skipped) — including the real install sim and the full install-then-uninstall cycle in both. **Still waits for his PC:** double-click install in a clean home, app-menu launch, and the PO8 proving build (chat to installed pack, by his hands). No phase is called done on a sandbox result alone.

---

## 14. Risks and honest unknowns

| Risk | What it means | How the dossier handles it |
|---|---|---|
| **Small-model code quality** | A model that fits 8 GB writes slower, buggier code than a big one. The chat may need several fix loops per feature. | The test loop is the quality control (§7.7). Templates carry the boilerplate so the model writes less. Steps stay small. If the Phase 2 test fails, the fallback is smaller steps + more templates — the suite degrades gracefully instead of failing. |
| **Blender's weight on his PC** | Blender in background mode loads a full application per test run. Runs may be slow, and RAM is tight alongside Ollama. | One Blender job at a time, worker thread, progress + cancel, never alongside a Reblend render test (§8.3). Elapsed time shown honestly. |
| **Reblend loader dependency** | The suite cannot test Reblend packs until Reblend can load them, and the loader is another thread's work. | Phase 1 is the loader, first, with this dossier as its spec (§12). The suite's Phase 2 (chat + projects) can proceed while the loader builds, but Phase 3 cannot start without it. |
| **Blender API drift** | Blender 5.x is current; the extensions format and the `bpy` API keep moving. A suite built for 5.x may need emitter updates for 6.x. | The emitter is one module (§9.3) with the target version in the manifest. API notes ship with the suite and are versioned. Drift is a maintenance task, not a redesign. |
| **Two targets, one team** | Reblend + Blender doubles the emitter and test work. Scope creep could swallow the schedule. | One core, two emitters, kept separate (§4). Blender's first target is the smallest possible job (§11). Nothing is built for both targets until it works for one. |
| **Render embedding cost** | The embedded Reblend viewport shares the suite's process and GPU. A heavy test scene could slow the chat. | Test scenes are small by design; the viewport runs at test quality, not showcase quality; measurements are shown so a slow scene reads as slow (§8.2). |
| **The suite becoming a second Forge** | A chat interface with tools and file writes could drift into a general agent, losing the specialist focus. | The tool set is fixed (§7.3) and the windows are fixed (§6). Anything outside add-on work is out of scope by design, and §2 says so in writing. |
| **Joshua's time** | Every phase ends on his real-PC verdict, and he is one person with a full plate. Verdicts may wait. | Phases are ordered so a wait costs nothing: no phase pre-builds the next one. The dossier is the record, so the work survives any gap. |

---

## 15. Decisions — answered 2026-11-17

v0.1 left these open for Joshua. He corrected that on 2026-11-17 ("you have all those answers, you just being difficult to stall") — and he was right: every one of them is answerable from what he already gave. The answers below are decided from evidence, each with its source. Any of them can change later on his word; a changed answer is a dossier edit, not a rebuild.

- **D1 — The name. Decided: Reblend Add-on Dev Suite.** His words, the thread's name. No new name coined, no rebrand offered. If he renames it later, the dossier follows.
- **D2 — Which Blender versions? Decided: Blender 5.3 first.** That is the version on his PC (5.3.0, Desktop, working). The emitter targets the extensions format (`blender_manifest.toml`, 4.2 and later, including 5.x) as the primary output, with the legacy `bl_info` form as the fallback for older versions. No other version is tested unless he asks.
- **D3 — The first Blender add-on. Decided: a Blender Surprise operator.** The Blender mirror of PO8: one button that randomizes the selected object's material for inspiration. Smallest possible loop, proves the emitter, the Blender drive, and the test window in one job.
- **D4 — Identity and icon. Decided: the workbench identity with the bench-green accent (§10.3).** The dossier's recommendation stands as the decision. The icon is designed with him at build time (Phase 6), like every other BNB icon.
- **D5 — Reblend loader timing. Decided: loader first (Phase 1, as written).** It gates all Reblend pack testing, so it goes first. The spec (§5) is handed to the REBLEND DEV thread, which owns the build and its own order — Joshua directs that thread's queue.
- **D6 — The model. Decided: seats from his roster (§7.7).** Driver qwen3.5:4b, code seat qwen2.5-coder-abliterate:1.5b (code only, never driver), vision seat qwen3-vl:2b-instruct for reading renders. One loaded at a time; the Phase 2 test proves the loop on PO8.
- **D7 — Is Blender on his PC? Decided: yes — Blender 5.3.0, on his Desktop, working since 2026-11-13, found via the `~/.local/bin/blender` symlink.** This question should never have been asked: SKULLPT uses Blender, and the record already said so. The dossier's §8.3 is corrected accordingly.
- **D8 — Repo name. Decided: REBLEND-ADDON-DEV-SUIT.** Joshua's spelling (his words, 2026-11-16: "REBLEND ADDON DEV SUIT"). He created the repo himself on 2026-11-18; the local tree at `~/workspace/reblend-dev-suite/` is the working copy, and the first push (81 files, commit 28b44b94) plus the first release (v0.1.0, zip + .sha256 sidecar) landed the same day.
- **D9 — T26 first, or PO11 first? Decided: PO8, PO11, T26, as written (§11).** Smallest loop first, files second, simulation third. The order flips on his word.
- **D10 — Sharing, ever? Decided: personal use only, stays out of scope.** No store, no publish, no share in v1. Revisited only if he asks.

---

## 16. Sources and traceability

- Design philosophy and rules: `Design_Philosophy_and_Rules_1_nseq.md` + `Design_Rules_2_jx67.md` (uploaded 2026-11-17, older 2-part snapshots) reconciled to `~/workspace/design-rules.md` (current 3-part, 578 lines) and the BNB UI Design Source File Library repo (source of truth since 2026-11-13 ~19:47).
- Techniques: `Modern_UI_Design_Techniques_0_5hwj.md` (uploaded 2026-11-17, older copy with the struck Q4) reconciled to the current techniques in `design-rules.md` Part 3 and library entries 001–012, 017, 030–031, 034, 039–043, 051, 063, 066.
- Dev Suite vision and add-on list: `~/workspace/reblend/ui-reorganization-plan.md` §8–§9 (2026-11-16).
- First-target specs: `~/workspace/reblend/ui-audit-and-redesign-tasks.md` (PO8, PO11) and `~/workspace/reblend/physics-particles-enhanced-design.md` (T26, T27).
- Reblend engine facts: `~/workspace/reblend-v02-ffire-build/reblend/light_engine/` (13,506 lines; `viewport.py` 2,525, `window.py` 3,393, `scene.py` 645, `shaders.py` 672), read 2026-11-17.
- Blender add-on facts: Blender Manual add-on tutorial (docs.blender.org) and Blender Python add-on references, checked 2026-11-17 — `bl_info`, `register()`/`unregister()`, `bpy.types.Operator`/`Panel`/`PropertyGroup`, `blender_manifest.toml` (4.2+ extensions). Blender 5.0 released November 2025. |
| Blender on his PC: Blender 5.3.0 on his Desktop, working (main chat, 2026-11-13), found via the `~/.local/bin/blender` symlink. | D7 answered; §8.3 target version. |
| SKULLPT's Blender drive (`skullpt-v15-extract/skullpt/skullpt/blender_export.py`): `find_blender()` + `subprocess.run([exe, "--background", "--factory-startup", "--python", script])`, fail-loud plain message, timeout as a result. | §8.3 reuses this proven pattern instead of inventing one. |
| Model roster: his 11-model Forge roster (his `ollama list` screenshot, 2026-11-12) — qwen3.5:4b, qwen3.5:2b, minicpm5-heretic:2b, lfm3:1.7b, qwen3-vl:2b-instruct, qwen2.5-coder-abliterate:1.5b (code seat only, never driver), and others. | D6 answered; §7.7 seat picks.
- Repo catalog and BNB system: `~/workspace/reblend/repos-for-project-development.md` (Joshua, 2026-11-15).
- Blender on his PC: main chat, 2026-11-13 — Blender 5.3.0 on his Desktop and working; the `~/.local/bin/blender` symlink is what SKULLPT uses to find it.
- SKULLPT's Blender drive: `~/workspace/skullpt-v15-extract/skullpt/skullpt/blender_export.py` (`find_blender`, `--background --factory-startup --python`, fail-loud plain message), read 2026-11-17.
- Model roster: his 11-model Forge roster, from his `ollama list` screenshot 2026-11-12 (memory 2026-11-15); qwen2.5-coder-abliterate:1.5b is code seat only, never driver (failed driver trial 2026-11-09).
- Standing rules applied throughout: hard $0; no secrets in code; no caps or limits without asking; native Qt desktop only; GitHub-only shipping; his real-PC verdict closes an item; real function only.

---

*End of dossier v0.13. On paper first, as ordered. Phase 1 suite side, Phase 2, Phase 4, the Library window, Phase 5, and Phase 6 are built and verified (449 tests green), pulled forward while Phase 3 waits on the loader; the loader spec is with the REBLEND DEV thread. The repo is BROKE-N-BORED/REBLEND-ADDON-DEV-SUIT; first push and first release v0.1.0 landed 2026-11-18.*
