# Changelog

## [0.60.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.60.0...beeagent-v0.60.1) (2026-09-14)


### Bug Fixes

* **rop:** make web projection lifecycle backward compatible ([#244](https://github.com/beesyst/beeagent/issues/244)) ([9337638](https://github.com/beesyst/beeagent/commit/9337638c6dbcca390f4c1fa908f2011d666fd4fd))

## [0.60.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.59.2...beeagent-v0.60.0) (2026-09-13)


### Features

* **rop:** add canonical source management and clean up tests ([556061d](https://github.com/beesyst/beeagent/commit/556061da1332eda424c6bf325e6244fe231bc34b))
* **rop:** add team leaderboard and scoped permissions ([5629a22](https://github.com/beesyst/beeagent/commit/5629a220a7209fd2e47a739600a27156e9ee5a19))


### Bug Fixes

* **rop:** Add attachment queue filter ([efe50bd](https://github.com/beesyst/beeagent/commit/efe50bd90212cfbfc05b5e04c067815597e7b046))
* **rop:** Clarify Bitrix queue statuses ([7c9640f](https://github.com/beesyst/beeagent/commit/7c9640fad694a302d2170eb814fd36218eafb8ba))
* **rop:** expose period comparison trends ([9c3dcd3](https://github.com/beesyst/beeagent/commit/9c3dcd3e74cf2dd149d94b9f791871e73e5fdccb))
* **rop:** finalize UI cleanup contracts ([4b7ac5b](https://github.com/beesyst/beeagent/commit/4b7ac5b6a8f9c40018fef9e6919a0e54151641d9))
* **rop:** improve event detail view ([76492f7](https://github.com/beesyst/beeagent/commit/76492f76c0cc8cf59fd0364aed018b3fbba2f975))
* **rop:** refresh projection after scoped writeback ([2947a32](https://github.com/beesyst/beeagent/commit/2947a32d34df5d773765e18669435ec44acf9875))
* **rop:** Remove AI assist tab ([bba3e3e](https://github.com/beesyst/beeagent/commit/bba3e3eecf2cf9deaba1986b0d0957ae2f8a69c9))
* **rop:** Remove attachments tab ([28f447b](https://github.com/beesyst/beeagent/commit/28f447beac743da00e4cfe48912035a14767690d))
* **rop:** Remove Bitrix tab ([e2ac5c4](https://github.com/beesyst/beeagent/commit/e2ac5c44234cc01ce235e34157cc542ba3bdfce2))
* **rop:** Remove evidence tab ([3225be0](https://github.com/beesyst/beeagent/commit/3225be0dc76586d688228743c27179552ceb239b))
* **rop:** remove obsolete action drafts ([8497483](https://github.com/beesyst/beeagent/commit/8497483903983de3fe3cbc06d1cb172950ee3855))
* **rop:** Remove ROP delivery recommendations ([f535af3](https://github.com/beesyst/beeagent/commit/f535af3684529a9463057ebfdc704dbbf2b7b987))
* **rop:** Remove threads tab ([0b05912](https://github.com/beesyst/beeagent/commit/0b05912b404a65f10ed9d6cd74cc4af0114f6a5d))
* **rop:** simplify event detail status ([813970b](https://github.com/beesyst/beeagent/commit/813970b99943a548536f40b0c29f5a531efdc9f4))
* **rop:** Simplify ROP overview ([8800485](https://github.com/beesyst/beeagent/commit/8800485ad56ed345e7b692a90a3fdf84bb98d9fc))

## [0.59.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.59.1...beeagent-v0.59.2) (2026-09-04)


### Bug Fixes

* **rop:** scope writeback recovery and preserve thread delivery ([#239](https://github.com/beesyst/beeagent/issues/239)) ([e1700bc](https://github.com/beesyst/beeagent/commit/e1700bcdd3509d08360c498e56ff04949e9691bb))

## [0.59.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.59.0...beeagent-v0.59.1) (2026-09-04)


### Bug Fixes

* **rop:** bound web projection retention ([#237](https://github.com/beesyst/beeagent/issues/237)) ([0e53c2a](https://github.com/beesyst/beeagent/commit/0e53c2abb03622607ecfeb6806a5e5d10be7a88d))

## [0.59.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.58.0...beeagent-v0.59.0) (2026-09-03)


### Features

* **rop:** add request-ready ROP Web projection v2 ([#235](https://github.com/beesyst/beeagent/issues/235)) ([6f6e401](https://github.com/beesyst/beeagent/commit/6f6e40185df35a06832c1f1997e50c55dc197f07))

## [0.58.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.57.2...beeagent-v0.58.0) (2026-09-03)


### Features

* add bounded table actions and ROP sender blacklist ([3294958](https://github.com/beesyst/beeagent/commit/3294958180a3411cccd29d585c672c9ee50c806d))
* **tables:** add bounded table actions ([2e3dac6](https://github.com/beesyst/beeagent/commit/2e3dac6aa62d7331c05baed8dda1f9b449a18842))


### Bug Fixes

* polish ROP blacklist UI ([3540ebc](https://github.com/beesyst/beeagent/commit/3540ebc3688e81eaa2bc5444bfc8db9a7fa7ac52))

## [0.57.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.57.1...beeagent-v0.57.2) (2026-09-02)


### Bug Fixes

* harden ROP duplicate evidence diagnostics ([5cd6292](https://github.com/beesyst/beeagent/commit/5cd629263d8efa8abbca9ee26a5e33b0925550d1))
* **rop:** detect ROP duplicates and attach same-subject emails ([cdd5295](https://github.com/beesyst/beeagent/commit/cdd5295141dd7c1aaa0163073800a856e25686b7))
* **rop:** harden duplicate handoff and Bitrix writeback ([90910bd](https://github.com/beesyst/beeagent/commit/90910bd92739e0c61b7269e8bdc6fa3f24863ba7))
* **rop:** reuse trusted lead for sender-subject follow-ups ([7049e92](https://github.com/beesyst/beeagent/commit/7049e929fc828c36dd03d715e6a367391121eb60))

## [0.57.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.57.0...beeagent-v0.57.1) (2026-08-30)


### Bug Fixes

* **rop:** harden projection lifecycle ([#226](https://github.com/beesyst/beeagent/issues/226)) ([4f4aaa5](https://github.com/beesyst/beeagent/commit/4f4aaa507e779529bb69b21db2e26cb994f4faf2))

## [0.57.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.56.2...beeagent-v0.57.0) (2026-08-28)


### Features

* auto-select Docling CPU/CUDA runtime profile ([#222](https://github.com/beesyst/beeagent/issues/222)) ([479d7ed](https://github.com/beesyst/beeagent/commit/479d7ed31273c336340b31b19c1d81c1ee4922cb))

## [0.56.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.56.1...beeagent-v0.56.2) (2026-08-27)


### Bug Fixes

* **startup:** make config an explicit package ([#220](https://github.com/beesyst/beeagent/issues/220)) ([f559f49](https://github.com/beesyst/beeagent/commit/f559f497d024026b18bb7e0230ab16153db55aec))

## [0.56.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.56.0...beeagent-v0.56.1) (2026-08-27)


### Bug Fixes

* **rop:** adopt BeeUI live search and pagination ([#218](https://github.com/beesyst/beeagent/issues/218)) ([f007fa0](https://github.com/beesyst/beeagent/commit/f007fa0fb83f4733464de4315a9e7aab8064d5cb))

## [0.56.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.55.0...beeagent-v0.56.0) (2026-08-27)


### Features

* **rop:** route matched and fallback new leads to separate bitrix stages ([#216](https://github.com/beesyst/beeagent/issues/216)) ([57caed2](https://github.com/beesyst/beeagent/commit/57caed2b94112d7b946a9a53394ae0aa4f5fd52b))

## [0.55.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.54.0...beeagent-v0.55.0) (2026-08-27)


### Features

* **attachments:** migrate document extraction to Docling ([32abc37](https://github.com/beesyst/beeagent/commit/32abc3715365d1dfaa0166b115f01192750fdbb1))


### Bug Fixes

* **bootstrap:** auto-prepare Docling assets on startup ([16b3f4f](https://github.com/beesyst/beeagent/commit/16b3f4fe7e217a3ccb77bc7a5587a54246bf72cb))

## [0.54.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.53.2...beeagent-v0.54.0) (2026-08-25)


### Features

* **rop:** secure ROP attachment lifecycle, download and Bitrix file delivery (it40) ([#210](https://github.com/beesyst/beeagent/issues/210)) ([4f280e7](https://github.com/beesyst/beeagent/commit/4f280e7c03811283643d113d0a0a95527bf92ab6))

## [0.53.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.53.1...beeagent-v0.53.2) (2026-08-23)


### Bug Fixes

* **rop:** cross-run continuation + locale ([044b0dd](https://github.com/beesyst/beeagent/commit/044b0ddc1b98361c835bb621e5974a877c4d71ca))
* **rop:** detect duplicates across runs ([0cf584f](https://github.com/beesyst/beeagent/commit/0cf584f8d1d0196debd64734701e56ddd61bf244))
* **rop:** harden Bitrix outbound correlation bridge ([c6a6074](https://github.com/beesyst/beeagent/commit/c6a607420a4452744fb5175b2c8cff773eafa568))
* **rop:** harden conversation identity and AI decision resolution ([034d74e](https://github.com/beesyst/beeagent/commit/034d74ed13efa020c7620242d2dab5d2e4db1cfb))
* **rop:** harden conversation identity, Bitrix correlation and AI adjudication ([7f1ec48](https://github.com/beesyst/beeagent/commit/7f1ec48f4702d64629bd2855acee0cd7102aa342))
* **rop:** keep CRM candidate evidence separate from new lead creation ([fd5f796](https://github.com/beesyst/beeagent/commit/fd5f7962ed2b314656ea99af81342653b8f591fd))
* **rop:** restore trusted Bitrix continuation classification ([133199a](https://github.com/beesyst/beeagent/commit/133199a68e64f15733f65dab7efe084f5dd374f3))

## [0.53.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.53.0...beeagent-v0.53.1) (2026-08-20)


### Bug Fixes

* **rop:** thread-aware Bitrix email write-back with trusted target provenance and readable body preview ([#204](https://github.com/beesyst/beeagent/issues/204)) ([69ee672](https://github.com/beesyst/beeagent/commit/69ee67234411cd70cf89afd76cf9205614bc71d7))

## [0.53.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.52.0...beeagent-v0.53.0) (2026-08-19)


### Features

* **it37:** add controlled bitrix CRM write-back ([#201](https://github.com/beesyst/beeagent/issues/201)) ([be47237](https://github.com/beesyst/beeagent/commit/be47237938abbaa1e47eb3f147c5aae05f62b517))

## [0.52.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.51.3...beeagent-v0.52.0) (2026-08-17)


### Features

* **rop:** multi-mailbox recipient routing and Bitrix responsible draft ([#195](https://github.com/beesyst/beeagent/issues/195)) ([c8c137d](https://github.com/beesyst/beeagent/commit/c8c137d64285147c50a6488ba41e7bee2ed8e454))

## [0.51.3](https://github.com/beesyst/beeagent/compare/beeagent-v0.51.2...beeagent-v0.51.3) (2026-08-14)


### Bug Fixes

* **rop:** repair thread context and adjudicate possible duplicates ([#192](https://github.com/beesyst/beeagent/issues/192)) ([7f8eaee](https://github.com/beesyst/beeagent/commit/7f8eaee44a2a0c94c063911e2cb328b310288dfb))

## [0.51.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.51.1...beeagent-v0.51.2) (2026-08-14)


### Bug Fixes

* **rop:** harden tender AI qualification ([#189](https://github.com/beesyst/beeagent/issues/189)) ([b716b90](https://github.com/beesyst/beeagent/commit/b716b9083691b33938cccff874d07a856be3061c))

## [0.51.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.51.0...beeagent-v0.51.1) (2026-08-13)


### Bug Fixes

* integrate duplicate-aware ROP classification into batch runtime ([#187](https://github.com/beesyst/beeagent/issues/187)) ([6b61e89](https://github.com/beesyst/beeagent/commit/6b61e89c4fd75ebf3a9c4bea69c239f222eed449))

## [0.51.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.50.2...beeagent-v0.51.0) (2026-08-12)


### Features

* **web:** enforce principal-scoped console access ([#184](https://github.com/beesyst/beeagent/issues/184)) ([39479f0](https://github.com/beesyst/beeagent/commit/39479f0cd3eef3619b3a15d3ec7233f440f1c245))

## [0.50.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.50.1...beeagent-v0.50.2) (2026-08-10)


### Bug Fixes

* **rop:** make dashboard run ordering deterministic ([#181](https://github.com/beesyst/beeagent/issues/181)) ([411523d](https://github.com/beesyst/beeagent/commit/411523d54c5852f232e62e3b2005aeb825f4c2e1))

## [0.50.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.50.0...beeagent-v0.50.1) (2026-08-10)


### Bug Fixes

* preserve ROP dashboard history across incremental mailbox runs ([#179](https://github.com/beesyst/beeagent/issues/179)) ([d3d17f4](https://github.com/beesyst/beeagent/commit/d3d17f4aa0173fe141ade7d4803560f4bdfc2dc9))

## [0.50.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.49.3...beeagent-v0.50.0) (2026-08-09)


### Features

* add ROP mailbox UID checkpoint polling ([#177](https://github.com/beesyst/beeagent/issues/177)) ([79ccc59](https://github.com/beesyst/beeagent/commit/79ccc598668df33f863f7ba983d8e70b4860d5d4))

## [0.49.3](https://github.com/beesyst/beeagent/compare/beeagent-v0.49.2...beeagent-v0.49.3) (2026-08-09)


### Bug Fixes

* tolerate malformed mailbox address headers ([#175](https://github.com/beesyst/beeagent/issues/175)) ([daf8b30](https://github.com/beesyst/beeagent/commit/daf8b301ed7c460a1d50a383fd24ea6eabd85403))

## [0.49.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.49.1...beeagent-v0.49.2) (2026-08-08)


### Bug Fixes

* preserve existing env permissions ([#173](https://github.com/beesyst/beeagent/issues/173)) ([b4b64ce](https://github.com/beesyst/beeagent/commit/b4b64ce9419eec225eb2bfde32b340d81abf3f7e))

## [0.49.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.49.0...beeagent-v0.49.1) (2026-08-08)


### Bug Fixes

* resolve storage root for symlinked deployments ([#171](https://github.com/beesyst/beeagent/issues/171)) ([0c778e0](https://github.com/beesyst/beeagent/commit/0c778e0342473abffb5e341326f164e16f802801))

## [0.49.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.48.2...beeagent-v0.49.0) (2026-08-02)


### Features

* **ui-8.5:** embed ROP console in Bitrix24 as local application with sso ([#169](https://github.com/beesyst/beeagent/issues/169)) ([26462a6](https://github.com/beesyst/beeagent/commit/26462a60aead7584f3741ff8850acad08626847e))

## [0.48.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.48.1...beeagent-v0.48.2) (2026-07-30)


### Bug Fixes

* **ui-8.4:** localize ROP decision explanations without duplicate AI … ([#167](https://github.com/beesyst/beeagent/issues/167)) ([b80f21a](https://github.com/beesyst/beeagent/commit/b80f21a68dc44373543fd7208bcd4eb3f1c5565d))

## [0.48.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.48.0...beeagent-v0.48.1) (2026-07-30)


### Bug Fixes

* **ui:** render semantic statuses in ROP Event Detail ([#165](https://github.com/beesyst/beeagent/issues/165)) ([6374efd](https://github.com/beesyst/beeagent/commit/6374efde380527ce5b5f39ee00a48e8292e6d462))

## [0.48.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.47.0...beeagent-v0.48.0) (2026-07-28)


### Features

* **ui:** adopt canonical ROP Queue table toolbar ([#161](https://github.com/beesyst/beeagent/issues/161)) ([f6b7694](https://github.com/beesyst/beeagent/commit/f6b7694381a4276573b3e832f22d33c92cff16e4))

## [0.47.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.46.0...beeagent-v0.47.0) (2026-07-27)


### Features

* **ui:** integrate BeeUI Tabler date range picker ([6c54696](https://github.com/beesyst/beeagent/commit/6c546966a90f170520c729cea3e01f55e446c666))

## [0.46.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.45.0...beeagent-v0.46.0) (2026-07-22)


### Features

* adapt web inteface design for improved user experience ([#152](https://github.com/beesyst/beeagent/issues/152)) ([3dbf7d9](https://github.com/beesyst/beeagent/commit/3dbf7d9cc53b323ba4af4976e398c5aee498fb42))

## [0.45.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.44.0...beeagent-v0.45.0) (2026-07-12)


### Features

* **ui:** add final decision read model and widget integration ([#149](https://github.com/beesyst/beeagent/issues/149)) ([0a498c8](https://github.com/beesyst/beeagent/commit/0a498c8646decdd5f809ebc8af945734efb0128b))

## [0.44.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.43.4...beeagent-v0.44.0) (2026-07-09)


### Features

* **rop:** add OpenAI adjudicator for ambiguous classifications ([#146](https://github.com/beesyst/beeagent/issues/146)) ([7b13021](https://github.com/beesyst/beeagent/commit/7b130212ca510630a6b6937444aba93fdd5f1323))

## [0.43.4](https://github.com/beesyst/beeagent/compare/beeagent-v0.43.3...beeagent-v0.43.4) (2026-07-06)


### Bug Fixes

* **rop:** correct forwarded original sender extraction ([#143](https://github.com/beesyst/beeagent/issues/143)) ([8ab99fd](https://github.com/beesyst/beeagent/commit/8ab99fdf33b93c8e3fae03db0566c9d6a8d0e1d3))

## [0.43.3](https://github.com/beesyst/beeagent/compare/beeagent-v0.43.2...beeagent-v0.43.3) (2026-07-01)


### Bug Fixes

* **rop:** normalize forwarded mailbox traffic ([#141](https://github.com/beesyst/beeagent/issues/141)) ([9536c3e](https://github.com/beesyst/beeagent/commit/9536c3ef7200931388e417aeecdad8b8ee80e488))

## [0.43.2](https://github.com/beesyst/beeagent/compare/beeagent-v0.43.1...beeagent-v0.43.2) (2026-07-01)


### Bug Fixes

* **rop:** resolve mailbox host and folder from env ([#138](https://github.com/beesyst/beeagent/issues/138)) ([49e4dfa](https://github.com/beesyst/beeagent/commit/49e4dfa3f82031f4a7142d88b16ea61afdc50790))

## [0.43.1](https://github.com/beesyst/beeagent/compare/beeagent-v0.43.0...beeagent-v0.43.1) (2026-07-01)


### Bug Fixes

* **bootstrap:** sync env and rotate internal secrets ([#136](https://github.com/beesyst/beeagent/issues/136)) ([cb52ef8](https://github.com/beesyst/beeagent/commit/cb52ef8dc286bcc3ed42803934f8b11d959bb3fa))

## [0.43.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.42.0...beeagent-v0.43.0) (2026-07-01)


### Features

* **rop:** add customer delivery MVP ([#134](https://github.com/beesyst/beeagent/issues/134)) ([038e722](https://github.com/beesyst/beeagent/commit/038e722f3a58ead23e73f6274bda4fe0dc1b9b9d))

## [0.42.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.41.0...beeagent-v0.42.0) (2026-06-30)


### Features

* **rop:** add review workbench event details ([#131](https://github.com/beesyst/beeagent/issues/131)) ([e2f9cbe](https://github.com/beesyst/beeagent/commit/e2f9cbeb0e7ff75b54ef77db4a69aba0a4c4d558))

## [0.41.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.40.0...beeagent-v0.41.0) (2026-06-30)


### Features

* **ui:** add BeeUI-backed auth boundary ([#127](https://github.com/beesyst/beeagent/issues/127)) ([6d742bf](https://github.com/beesyst/beeagent/commit/6d742bf3f6efa154ddfc64bc3cc34b01e26fa19a))

## [0.40.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.39.0...beeagent-v0.40.0) (2026-06-29)


### Features

* **ui:** expose ROP It30 evidence in BeeUI console ([#124](https://github.com/beesyst/beeagent/issues/124)) ([0551f7e](https://github.com/beesyst/beeagent/commit/0551f7eb8d66358f062ee3ec8d711b31b6fc094d))

## [0.39.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.38.0...beeagent-v0.39.0) (2026-06-29)


### Features

* **rop:** add latest-n thread context and ai assist execution ([#121](https://github.com/beesyst/beeagent/issues/121)) ([e2f10c4](https://github.com/beesyst/beeagent/commit/e2f10c4c0b77d3d73d565e81c928a79aec09d3d7))

## [0.38.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.37.0...beeagent-v0.38.0) (2026-06-24)


### Features

* **rop:** add Bitrix match quality gate and action drafts ([#118](https://github.com/beesyst/beeagent/issues/118)) ([c775e3a](https://github.com/beesyst/beeagent/commit/c775e3ae2fac7babc06243ba94e9ba69f99e5317))

## [0.37.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.36.0...beeagent-v0.37.0) (2026-06-23)


### Features

* **rop:** add MVP handoff readiness pack ([#115](https://github.com/beesyst/beeagent/issues/115)) ([b47a60d](https://github.com/beesyst/beeagent/commit/b47a60d4f20fd684f3da75b91060562943e2de1a))

## [0.36.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.35.0...beeagent-v0.36.0) (2026-06-21)


### Features

* **rop:** add business dashboard period analytics ([#111](https://github.com/beesyst/beeagent/issues/111)) ([7476a21](https://github.com/beesyst/beeagent/commit/7476a2186ac18721792c563d7c8a92ffd2e8a03e))

## [0.35.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.34.0...beeagent-v0.35.0) (2026-06-20)


### Features

* **rop:** add current-state index and Bitrix evidence board ([#108](https://github.com/beesyst/beeagent/issues/108)) ([ed92381](https://github.com/beesyst/beeagent/commit/ed92381560861d5ad0eba0a09f2f0cd0ec72c97a))

## [0.34.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.33.0...beeagent-v0.34.0) (2026-06-18)


### Features

* **bitrix:** add read-only reconciliation artifacts ([#105](https://github.com/beesyst/beeagent/issues/105)) ([dcde895](https://github.com/beesyst/beeagent/commit/dcde895fc95f6701a240b40ba8232bf9d3d99207))

## [0.33.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.32.0...beeagent-v0.33.0) (2026-06-16)


### Features

* **ui:** add rich ROP dashboard ([8cdca60](https://github.com/beesyst/beeagent/commit/8cdca60e4fb7838626296dba051c1765dd98f293))

## [0.32.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.31.0...beeagent-v0.32.0) (2026-06-12)


### Features

* **ui:** add BeeUI ROP operator console ([#98](https://github.com/beesyst/beeagent/issues/98)) ([8285afd](https://github.com/beesyst/beeagent/commit/8285afd45849e77a644cfad4df57ce6a63b3fc2f))

## [0.31.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.30.0...beeagent-v0.31.0) (2026-05-28)


### Features

* **rop:** add attachment extraction artifacts ([#93](https://github.com/beesyst/beeagent/issues/93)) ([0a3061c](https://github.com/beesyst/beeagent/commit/0a3061c177ef31fef947835d361edf654fb97794))

## [0.30.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.29.0...beeagent-v0.30.0) (2026-05-28)


### Features

* **ui:** add ROP multi-source dashboard ([#90](https://github.com/beesyst/beeagent/issues/90)) ([acab18a](https://github.com/beesyst/beeagent/commit/acab18a8929a94ff2756cb1c0d699812315ad8da))

## [0.29.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.28.0...beeagent-v0.29.0) (2026-05-27)


### Features

* **rop:** add multi-source ingestion artifacts ([#87](https://github.com/beesyst/beeagent/issues/87)) ([526c2cf](https://github.com/beesyst/beeagent/commit/526c2cf440890cc8e26a58c23e3d449debee3c02))

## [0.28.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.27.0...beeagent-v0.28.0) (2026-05-26)


### Features

* **ui:** add FastAPI Tabler Web Console foundation ([#84](https://github.com/beesyst/beeagent/issues/84)) ([66678ff](https://github.com/beesyst/beeagent/commit/66678ffc87c98595daafd22a73717fdd1606179b))

## [0.27.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.26.0...beeagent-v0.27.0) (2026-05-26)


### Features

* **rop:** harden source profile contract ([#81](https://github.com/beesyst/beeagent/issues/81)) ([43ab308](https://github.com/beesyst/beeagent/commit/43ab308fa84dcfbac7ffa13b0c37c212c7421776))

## [0.26.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.25.0...beeagent-v0.26.0) (2026-05-25)


### Features

* **web:** add operator shell with ROP dashboard ([#78](https://github.com/beesyst/beeagent/issues/78)) ([87d7e54](https://github.com/beesyst/beeagent/commit/87d7e54ea5b85db2a836b0ca492100f211328a36))

## [0.25.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.24.0...beeagent-v0.25.0) (2026-05-20)


### Features

* **rop:** enrich review TSV export ([#75](https://github.com/beesyst/beeagent/issues/75)) ([e6bc68e](https://github.com/beesyst/beeagent/commit/e6bc68e233f0f538a26a9d6d8d92a7051d1154b6))

## [0.24.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.23.0...beeagent-v0.24.0) (2026-05-17)


### Features

* **rop-cli:** add ROP run and review export ([#72](https://github.com/beesyst/beeagent/issues/72)) ([e8949fb](https://github.com/beesyst/beeagent/commit/e8949fb2cf0b85a8b37c9d7114aae582bb96cb5d))

## [0.23.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.22.0...beeagent-v0.23.0) (2026-05-10)


### Features

* **rop:** add live batch classification handoff ([#69](https://github.com/beesyst/beeagent/issues/69)) ([34e642c](https://github.com/beesyst/beeagent/commit/34e642c52ff98f881282f5d52c13f727675ff669))

## [0.22.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.21.0...beeagent-v0.22.0) (2026-05-08)


### Features

* **rop:** add mailbox read-only source ([#66](https://github.com/beesyst/beeagent/issues/66)) ([f388796](https://github.com/beesyst/beeagent/commit/f388796cff15f1f471d491cd1a6e1036822444db))

## [0.21.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.20.0...beeagent-v0.21.0) (2026-05-08)


### Features

* **rop:** add input source contract and batch handoff ([#63](https://github.com/beesyst/beeagent/issues/63)) ([fe5c281](https://github.com/beesyst/beeagent/commit/fe5c2814f095f895a4fff6810509e1269e5481ac))

## [0.20.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.19.0...beeagent-v0.20.0) (2026-05-01)


### Features

* **rop:** add operator run flow ([#60](https://github.com/beesyst/beeagent/issues/60)) ([4f75f96](https://github.com/beesyst/beeagent/commit/4f75f96c8078bb25fa98cada818732f82247c9dc))

## [0.19.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.18.0...beeagent-v0.19.0) (2026-04-30)


### Features

* **module:** integrate beeagent-rop runtime dispatch ([#57](https://github.com/beesyst/beeagent/issues/57)) ([a1f80b5](https://github.com/beesyst/beeagent/commit/a1f80b5fef4b6708334940c69a993080b4b7db82))

## [0.18.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.17.0...beeagent-v0.18.0) (2026-04-29)


### Features

* **core:** add capability boundary v0 ([#54](https://github.com/beesyst/beeagent/issues/54)) ([97ce305](https://github.com/beesyst/beeagent/commit/97ce30523b862961ec1f48ce41357673da93534d))

## [0.17.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.16.0...beeagent-v0.17.0) (2026-04-22)


### Features

* **core:** add runtime context and artifact api v0 ([#51](https://github.com/beesyst/beeagent/issues/51)) ([0536059](https://github.com/beesyst/beeagent/commit/0536059bcc3b606c384caad214c74f9708948bfd))

## [0.16.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.15.0...beeagent-v0.16.0) (2026-04-21)


### Features

* **core:** add local module registry v0 ([#48](https://github.com/beesyst/beeagent/issues/48)) ([0874ac6](https://github.com/beesyst/beeagent/commit/0874ac6bc1bfb5522c0133b3275f8da95e8ee216))

## [0.15.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.14.0...beeagent-v0.15.0) (2026-04-21)


### Features

* **core:** add internal module contract v0 ([#45](https://github.com/beesyst/beeagent/issues/45)) ([938fca0](https://github.com/beesyst/beeagent/commit/938fca0ab2beb698da1f1d65e29f5e85641a3648))

## [0.14.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.13.0...beeagent-v0.14.0) (2026-02-22)


### Features

* **telegram:** add AI Q&A over last OOS run artifacts ([6334883](https://github.com/beesyst/beeagent/commit/63348831267aec150fa0a043f1e602d628089aae))

## [0.13.0](https://github.com/beesyst/beeagent/compare/beeagent-v0.12.0...beeagent-v0.13.0) (2026-02-22)


### Features

* **i18n:** add ru translations and prompts config for telegram and o… ([993693c](https://github.com/beesyst/beeagent/commit/993693caf7624ff80d094e92104554aabbf0e92b))
* **i18n:** add ru translations and prompts config for telegram and oos report ([261b9f6](https://github.com/beesyst/beeagent/commit/261b9f6c62e41c1851177f3f0b0fc21147ef4491))

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
