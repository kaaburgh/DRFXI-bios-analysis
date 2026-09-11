# Next-chat handoff — DRFXI BIOS analysis

Важно. Это продолжение долгого reverse-engineering исследования BIOS MINISFORUM BD790i / DRFXI.

Главный репозиторий проекта:

https://github.com/kaaburgh/DRFXI-bios-analysis

Считай GitHub репозиторий главным persistent source of truth. Не начинай исследование с нуля и не полагайся только на этот handoff: сначала прочитай актуальное состояние из репо через GitHub connector.

## 1. Сначала восстанови состояние проекта

Обязательно прочитай:

- `docs/research-status.md`
- `docs/work-queue.md`
- `docs/findings/changelog-mapping.md`

Затем прочитай только relevant checkpoints/findings для выбранного следующего направления.

Особенно важные текущие checkpoints:

- `docs/checkpoints/2026-09-11-pi-1.0.0.3h-first-pass.md`
- `docs/checkpoints/2026-09-11-pi-1.0.0.3h-cve-2024-36311.md`

Intel LAN:

- `docs/findings/intel-lan-oprom.md`
- `docs/checkpoints/2026-09-11-intel-lan-oprom-source-dependencies-closure.md`
- и соседние `intel-lan-oprom` checkpoints, если нужны детали цепочки.

TCC:

- `docs/findings/tcc-pcd-consumer.md`

SMU:

- `docs/findings/smu-power-limit.md`
- `docs/deferred/smu-power-limit-deep-dive.md`

S3:

- `docs/findings/s3-workaround.md`

Сначала дай мне короткое восстановленное состояние:
- что завершено;
- что paused/deferred;
- что реально Ready for next bounded investigation;
- какие внешние артефакты нужны для paused branches.

Не предлагай новый branch, пока не прочитал `work-queue` и `research-status`.

## 2. Важные установленные результаты

Firmware corpus:

### DRFXI 1.12
SHA256:
`246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9`

### DRFXI 1.15
SHA256:
`3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88`

### DRFXI 1.17
SHA256:
`99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51`

Missing but confirmed:
- 1.13 — 2025-09-28, checksum `BF21`
- 1.14 — 2025-11-13, checksum `419D`
- 1.16 — 2026-06-03, checksum `1EA3`

Поэтому:
- 1.12→1.15 нельзя автоматически приписывать 1.13;
- 1.15→1.17 нельзя автоматически приписывать 1.16.

Обязательно разделяй:
- direct binary evidence;
- public/upstream correlation;
- inference;
- temporal attribution.

## 3. Какие ветки сейчас НЕ надо продолжать

### Intel LAN OPROM

Paused.

Установлено:
- problematic Intel LAN OPROM вероятнее всего принадлежит внешней/add-in PCIe NIC;
- onboard `LanRomDriver` — Realtek;
- generic firmware chain закрыта отрицательно:
  `PCIR parsing → OptionRomPolicy → EFI decompression → LoadImage → Security2 → PE/COFF → StartImage → protocol installation → synchronous RegisterProtocolNotify callbacks → DriverBinding / ConnectController`;
- Legacy/CSM route также практически исключён;
- ближайший network stack byte-identical;
- точная problem NIC неизвестна;
- Intel X710-DA2 / `I40eUndiDxe` — лучший найденный BD790i-specific кандидат, но НЕ доказанный reproducer.

Не продолжай generic firmware reverse engineering этой ветки.

Разблокировка:
- получить actual Option ROM X710-DA2 или, лучше, точную NIC/ROM исходного reproducer.

### PI 1.0.0.3h / CVE-2024-36311 SMM TOCTOU

Paused.

Установлено:
- AMD связывает DragonRangeFL1PI 1.0.0.3h с mitigation CVE-2024-36311;
- CVE — TOCTOU вокруг SMM communications buffer;
- public disclosure НЕ даёт module / handler GUID / communication GUID / function / patch / exact race shape;
- generic EDK2 `PiSmmCommunication` / `PiSmmCore` / `SmmMemLib` — только correlation.

Не делай generic SMM diff и не выбирай кандидата просто по `SmmIsBufferOutsideSmmValid`.

Разблокировка:
- concrete implementation fingerprint;
- source patch;
- researcher disclosure;
- strong cross-platform pre/post mitigation comparison;
- либо recovered 1.13 + независимое narrowing evidence.

### Update SMU for power limit

Paused.

Установлена замена embedded SMU firmware:
`0.54.68.0 → 0.54.6C.32`.

Raw byte diff нельзя интерпретировать напрямую из-за сильного layout movement.

Не продолжай raw byte diffing.

Разблокировка:
- reusable Ghidra/Xtensa-le environment / tooling, если это направление снова станет приоритетным.

### S3 / PCIe power-resume

Paused.

Найден `AmdCpmOemAcpi` / SSDT machinery и `PME_Turn_Off → WakeLink → DL_ACTIVE` path.

Лучший unblocker:
- DRFXI 1.16 или полезный runtime evidence.

## 4. Уже завершённые / почти завершённые результаты

### Set TCC to 100

Практически закрыто:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

Очень высокая уверенность.

Не повторять этот анализ без отдельной причины.

### PI 1.0.0.3h first pass

Три новых named PE между 1.12 и 1.15 классифицированы.

`AmdVariableProtection.efi` + `GenerateTimeBaseVariable.efi` образуют coherent AMD variable-protection cluster.

`AmdVariableProtection`:
- защищает `AMD_PBS_SETUP` / `AmdSetupRPL` / `AodSetupRpl`;
- использует VariablePolicy / VarCheck;
- generic `NvramDxe` provider семантически не изменён;
- управляет `AmdVariableProtection` variable;
- companion application генерирует authenticated create/delete payloads.

`HardwareSignatureEntry.efi`:
- отдельная AMI HardwareChange / ACPI FACS hardware-signature feature;
- не объединять автоматически с AMD VariableProtection cluster.

MMCONFIG / ECAM:
- 1.12: `0xF0000000`
- 1.15: `0xE0000000`

Это реальный platform-wide delta, замеченный как минимум в:
- `AmdNbioIOMMUDxe`
- `PciRootBridge`

Но прямой связи с VariableProtection/HardwareSignature cluster нет.

## 5. Методология сравнения

Очень важно:

Не считать:

`PE hash изменился` = `поведение изменилось`.

Во многих модулях уже обнаружены:
- PCD token renumbering;
- relocation noise;
- image-layout shifts;
- build timestamps;
- compiler noise;
- global platform constants.

Перед любым выводом делай normalization.

Для changed function сравнивай:
- control flow;
- immediates после классификации;
- call targets по semantic role;
- RIP-relative refs после relocation normalization;
- data structures;
- branches;
- protocol/variable GUID usage.

Нужно отделять:
1. build/relocation noise
2. PCD renumbering
3. shared platform constant changes
4. real data changes
5. real executable logic changes

## 6. Как работать по turns

Исследование должно идти короткими bounded passes.

Обычный turn:
1. Восстановить state из GitHub.
2. Выбрать ОДИН узкий вопрос.
3. Явно перечислить:
   - starting facts;
   - scope;
   - out-of-scope;
   - stop conditions.
4. Работать примерно 20–25 минут максимум.
5. Не расширять scope из-за отсутствия результата.
6. Negative result считать нормальным результатом.
7. После materially useful finding сразу записать его в GitHub.
8. Не ждать конца прохода для commits.
9. В конце обязательно сделать checkpoint.

Формат финального checkpoint:
- confirmed findings;
- semantic deltas;
- hypotheses + confidence;
- negative results;
- что НЕ доказано;
- почему остановились;
- один следующий самый узкий шаг.

Если направление упёрлось во внешний blocker:
- поставить его paused/deferred в GitHub;
- явно записать unblock condition.

## 7. Работа с GitHub

Используй GitHub connector напрямую.

Repository:
`kaaburgh/DRFXI-bios-analysis`

При начале нового направления создавай dated checkpoint, например:

`docs/checkpoints/2026-09-11-<topic>.md`

или актуальную дату нового чата.

Существенные findings фиксируй немедленно.

Living docs:
- `docs/research-status.md`
- `docs/work-queue.md`
- `docs/findings/changelog-mapping.md`

обновлять только когда вывод реально изменился.

Не переписывать старые dated checkpoints: они исторические/immutable.

Перед edit:
- сначала fetch текущую версию файла и SHA.

После каждого meaningful commit:
- сообщай commit SHA.

## 8. Локальные / firmware tools

Для UEFI анализа ранее использовались:
- UEFIExtract
- UEFIFind
- IFR extractor
- objdump / binutils
- Python для binary diff / GUID scan / normalization
- ACPICA / iasl для ACPI/AML, когда это действительно относится к задаче

В старом чате был подготовлен bundled UEFI toolchain с несколькими версиями UEFIExtract.

Если в новом чате локальных архивов/firmware уже нет:
- НЕ делай вид, что они доступны;
- сначала проверь доступные uploads / File Library;
- если binaries/toolchain отсутствуют — скажи, что нужно пере-загрузить.

Полезные старые артефакты назывались примерно:
- `bd790i-acquisition-return-20260910-102715.zip`
- `bd790i-uefi-toolchain-20260910T104754Z.tar.gz`
- `bd790i-acpica-toolchain-20260910T125624Z.tar.gz`

Но GitHub является главным носителем результатов, а не эти временные файлы.

## 9. Web/public research

Используй web search только когда нужен:
- AMD advisory;
- AMI/EDK2/public source-family;
- CVE data;
- board/user reports;
- upstream patch/version mapping;
- firmware mirror / missing version recovery.

Всегда отделяй public evidence от inference.

GitHub public-source code ищи через GitHub connector, если это GitHub.

Не подменяй отсутствие evidence общими знаниями о UEFI/AGESA.

## 10. Приоритеты

Не выбирай новый branch по памяти.

После чтения:
- `docs/research-status.md`
- `docs/work-queue.md`
- `docs/findings/changelog-mapping.md`

предложи 1–3 реально доступных bounded next steps.

Предпочитать:
- evidence-driven;
- узкие;
- с хорошим expected information gain;
- без необходимости общего reverse engineering.

Сейчас многие ветки intentionally paused, поэтому recovery missing firmware или хорошо ограниченный unexplained delta может быть ценнее ещё одного глубокого RE.

## 11. Стиль выводов

Для важных исследовательских ответов начинай итог с:

`❕ TL;DR:`

Не завышай уверенность.

Используй формулировки:
- CONFIRMED
- STRONG EVIDENCE
- CORRELATION
- INFERENCE
- NOT PROVEN

где это помогает.

Нельзя писать:
`это точно изменение из 1.13`
если evidence только 1.12→1.15.

Нельзя выбирать firmware module только потому, что его название похоже на искомую функцию.

## 12. Первый turn нового чата

Сейчас не начинай новый reverse-engineering pass.

Сначала:
1. прочитай через GitHub:
   - `docs/research-status.md`
   - `docs/work-queue.md`
   - `docs/findings/changelog-mapping.md`
2. при необходимости прочитай последние checkpoints;
3. дай мне краткий reconstructed project state;
4. предложи следующие 2–3 bounded направления, отсортированные по expected information gain;
5. для каждого скажи:
   - что именно проверяем;
   - какие артефакты уже есть;
   - чего не хватает;
   - stop condition;
   - примерный 20–25 минутный scope.

После моего выбора уже начинай исследование.
