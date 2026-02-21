# Changelog

## [0.12.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.11.0...beeagent-v0.12.0) (2026-02-21)


### Features

* **llm:** move responses api_url to settings and fix client ([e79efc0](https://github.com/beesyst/beeagent/commit/e79efc0836373932ed3a9a83135409d0549677f4))


### Bug Fixes

* **llm:** add throttling retry on timeout for responses api ([e5ef348](https://github.com/beesyst/beeagent/commit/e5ef348fa7227ff87335bc046fa81ed8a82f829b))
* **llm:** remove temperature and use responses api ([d4eacf2](https://github.com/beesyst/beeagent/commit/d4eacf2a6ab1be3bcbaba1b7e282818e6c4f5ffb))

## [0.11.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.10.0...beeagent-v0.11.0) (2026-02-21)


### Features

* **oos:** add explainable recommendations and optional llm summary ([230869d](https://github.com/beesyst/beeagent/commit/230869d881cb0ec49df8a8a2fdc1325ed0dd1681))

## [0.10.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.9.0...beeagent-v0.10.0) (2026-02-20)


### Features

* **quiz:** add telegram pharmacy quiz with artifacts and last result ([7ad71f4](https://github.com/beesyst/beeagent/commit/7ad71f4ec4ceb0295b3b9293bed31d1ea02aaf12))

## [0.9.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.8.0...beeagent-v0.9.0) (2026-02-20)


### Features

* **agents:** add promo agent v0 with telegram command and artifacts ([cb43c18](https://github.com/beesyst/beeagent/commit/cb43c185da056b3905a57b36456f46858224629e))

## [0.8.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.7.0...beeagent-v0.8.0) (2026-02-19)


### Features

* **oos:** add steps timing and steps.json trace ([c4d53b1](https://github.com/beesyst/beeagent/commit/c4d53b15db4f541180894838de3db17c75bbe456))

## [0.7.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.6.0...beeagent-v0.7.0) (2026-02-19)


### Features

* **scheduler:** add periodic scheduled OOS runs with mandatory approval ([411fd32](https://github.com/beesyst/beeagent/commit/411fd32793c5f76193a94ad3ac364a9b7f2cdd39))

## [0.6.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.5.0...beeagent-v0.6.0) (2026-02-19)


### Features

* **core:** add cases layer and data adapter for OOS workflow ([a9a463b](https://github.com/beesyst/beeagent/commit/a9a463bb231990eabee4741e060f98942fa0401c))

## [0.5.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.4.0...beeagent-v0.5.0) (2026-02-18)


### Features

* **approval:** add task approval and report export artifacts ([1bd5d25](https://github.com/beesyst/beeagent/commit/1bd5d257add05a6eca2dd16a31af73698e548def))
* **oos:** add langgraph workflow v0 ([993b0a3](https://github.com/beesyst/beeagent/commit/993b0a329e6c1ca4a529826d6f62fcc75815b76f))

## [0.4.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.3.0...beeagent-v0.4.0) (2026-02-18)


### Features

* **mock:** add deterministic dataset generator and domain model ([a1ba1c4](https://github.com/beesyst/beeagent/commit/a1ba1c42896e1119de771d9fe49a49a6f83d7a98))

## [0.3.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.2.1...beeagent-v0.3.0) (2026-02-18)


### Features

* **telegram:** add bot ux skeleton with allowlist and telemetry ([f0ab046](https://github.com/beesyst/beeagent/commit/f0ab04612dc4e6a6e673954ae71a49a66fb81432))


### Bug Fixes

* remove versions.yml ([1389c0f](https://github.com/beesyst/beeagent/commit/1389c0fe6aec642fcf0b79e4949e48d695c0180a))

## [0.2.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.2.0...beeagent-v0.2.1) (2026-02-18)


### Bug Fixes

* **ci:** remove initial-version from release-please config ([eb7fe05](https://github.com/beesyst/beeagent/commit/eb7fe05297d348d65103380c7fb0e5b28687ad8b))
* **ci:** remove initial-version from release-please config ([6fe6f5b](https://github.com/beesyst/beeagent/commit/6fe6f5bf2ad7b0e74d0853a103be83306914063b))

## [0.2.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.1.0...beeagent-v0.2.0) (2026-02-17)


### Features

* iteration 0 skeleton and launch ([b154a54](https://github.com/beesyst/beeagent/commit/b154a5415d287ef97a7f7aed69f694ff507423a8))


### Bug Fixes

* **ci:** init release-please manifest ([4fb8a30](https://github.com/beesyst/beeagent/commit/4fb8a3070fbe481b9042658dd7d87c68a54e54de))
* **ci:** set release-please initial version to 0.1.0 ([d7eed7d](https://github.com/beesyst/beeagent/commit/d7eed7df84610ebebaa21341162a81000318207e))
