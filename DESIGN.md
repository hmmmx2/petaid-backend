# PetAid Detailed Design — Assignment 3

This document accompanies the source code as the **Detailed Design** deliverable for SWE30003 Assignment 3. It explains how the high-level OO design from Assignment 2 has been refined for implementation, justifies every deviation from the original UML, lists the design patterns and heuristics that are actually realised in code, and points at the matching files.

The Assignment 2 SRS lives in `Group10_Software Requirements Specification (SRS) Assignment 2.pdf`.

---

## 1. Mapping UML → code

| UML class (SRS §3) | Implementation                          | File |
| --- | --- | --- |
| `AppController` «singleton» | `AppController` (metaclass `_SingletonMeta`) | [app/domain/app_controller.py](app/domain/app_controller.py) |
| `AuthManager` | `AuthManager` (factory for Account hierarchy) | [app/domain/auth_manager.py](app/domain/auth_manager.py) |
| `PaymentProcessor` | Abstract `PaymentProcessor` + `MockPaymentProcessor` (Adapter) | [app/domain/payment_processor.py](app/domain/payment_processor.py) |
| `MediaStorage` | `MediaStorage` validator | [app/domain/media_storage.py](app/domain/media_storage.py) |
| `Dashboard` «abstract» | `Dashboard` ABC (Template Method) | [app/domain/dashboards.py](app/domain/dashboards.py) |
| `PetOwnerDashboard` | `PetOwnerDashboard(Dashboard)` | [app/domain/dashboards.py](app/domain/dashboards.py) |
| `VeterinaryExpertDashboard` | `VeterinaryExpertDashboard(Dashboard)` | [app/domain/dashboards.py](app/domain/dashboards.py) |
| `Account` «abstract» | `Account` (single-table inheritance, polymorphic discriminator `role`) | [app/models/account.py](app/models/account.py) |
| `PetOwner` «actor» | `PetOwner(Account)` | [app/models/account.py](app/models/account.py) |
| `VeterinaryExpert` «actor» | `VeterinaryExpert(Account)` | [app/models/account.py](app/models/account.py) |
| `Pet` «entity» | `Pet` | [app/models/pet.py](app/models/pet.py) |
| `PetType` «entity» | `PetType` | [app/models/pet_type.py](app/models/pet_type.py) |
| `FirstAidGuidance` «entity» | `FirstAidGuidance` | [app/models/first_aid.py](app/models/first_aid.py) |
| `Resource` «entity» | `Resource` (+ `ResourceStatus`) | [app/models/resource.py](app/models/resource.py) |
| `Quiz` «entity» | `Quiz`, `QuizAttempt` | [app/models/quiz.py](app/models/quiz.py) |
| `Inquiry` «entity» | `Inquiry`, `InquiryStatus` | [app/models/inquiry.py](app/models/inquiry.py) |
| `Chat` «entity» | `Chat`, `ChatMessage`, `ChatStatus` | [app/models/chat.py](app/models/chat.py) |
| `Donation` «entity» | `Donation`, `DonationStatus` | [app/models/donation.py](app/models/donation.py) |
| `Feedback` «entity» | `Feedback`, `FeedbackTargetType` | [app/models/feedback.py](app/models/feedback.py) |
| `UserCredentials` «data-holder» | `UserCredentials` (1:1 composition) | [app/models/credentials.py](app/models/credentials.py) |
| `DonationRecord» «data-holder» «immutable» | `DonationRecord` (composed, never mutated post-create) | [app/models/donation.py](app/models/donation.py) |
| `FeedbackEntry` «data-holder» | `FeedbackEntry` (1:1 composition) | [app/models/feedback.py](app/models/feedback.py) |

Every class from SRS Figure 1 is present. No new classes were introduced and none were dropped at the implementation stage.

---

## 2. Design patterns realised in code

| Pattern | SRS § | Where to look |
| --- | --- | --- |
| **Singleton** | 5.1.2 | `_SingletonMeta` metaclass in [app_controller.py](app/domain/app_controller.py). Used by `AppController`. The metaclass is shareable, so additional singletons can be added without copy-paste. |
| **Factory Method** | 5.1.1 | `AuthManager._make_account` in [auth_manager.py](app/domain/auth_manager.py) — selects `PetOwner` vs `VeterinaryExpert` based on the requested role. The router calls only `AuthManager.register(...)`, never `PetOwner(...)` or `VeterinaryExpert(...)` directly. |
| **Template Method** | 5.2.2 | `Dashboard.render` in [dashboards.py](app/domain/dashboards.py). The skeleton (user summary, role, panel envelope) lives on the base class; `_panels` is abstract and supplied by each subclass. |
| **Observer** | 5.2.1 | `EventBus` in [events.py](app/domain/events.py). `Inquiry`, `Chat`, `Donation` and `Feedback` publish on submission/state transitions; the default subscriber logs each event. Real-world notification sinks (email, push) plug in as additional subscribers in `AppController._wire_default_subscribers`. |
| **Adapter** | 5.3.1 | `PaymentProcessor` (abstract) and `MockPaymentProcessor` / `FailingPaymentProcessor` in [payment_processor.py](app/domain/payment_processor.py). The `Donation` entity calls only the abstract interface; swapping the concrete adapter does not require changes elsewhere. |

---

## 3. Heuristics realised in code

The Riel (1996) heuristics listed in SRS §4.1 are enforced via review and structure:

1. **One key abstraction per class** — Each domain class has a single docstring stating its purpose. Authentication lives only in `AuthManager`; media only in `MediaStorage`; payment only in `PaymentProcessor`.
2. **Data hiding and encapsulation** — `UserCredentials` is in its own table and is read only by `AuthManager`. `DonationRecord` is an immutable composed table — no method on the codebase mutates one after insert. `FeedbackEntry` lives inside `Feedback`.
3. **Avoid god classes** — `AppController` does not authenticate, render, or persist directly. It wires `AuthManager`, picks the right `Dashboard` subclass, and owns the `EventBus`. Routers are thin HTTP adapters; behaviour lives on entities (`Inquiry.respond`, `Chat.join`, `Quiz.evaluate`) or services.
4. **Even distribution of intelligence** — Each entity owns its own state transitions. `Quiz.evaluate(answers) -> (score, passed)` is on `Quiz`, not on a router or service.
5. **Minimal public interface** — `AuthManager` exposes only `register` and `authenticate`. `MediaStorage` only `accept` and `retrieve`. `PaymentProcessor` only `charge`. Internal helpers are `_underscore`-prefixed.
6. **Inheritance for specialisation only** — Two inheritance hierarchies: `Account → PetOwner/VeterinaryExpert` (different actor capabilities) and `Dashboard → PetOwnerDashboard/VeterinaryExpertDashboard` (different views). Both are genuine "kind-of" relationships.
7. **Composition for strong ownership** — `Account` ↔ `UserCredentials`, `Donation` ↔ `DonationRecord`, `Feedback` ↔ `FeedbackEntry` are all declared with `cascade="all, delete-orphan"` and `uselist=False` 1:1 relationships.
8. **Beware of data-only classes** — Only three exist (`UserCredentials`, `DonationRecord`, `FeedbackEntry`), each justified by encapsulation or immutability requirements.

---

## 4. Changes from Assignment 2 — what, why, where

| Change | Where | Why |
| --- | --- | --- |
| Spelling normalised to `FirstAidGuidance` in code | UML labels alternate between `FirstAidguidance` and `FirstAidGuidance`. Python class names must use PascalCase consistently. | PEP 8 ([style guide](https://peps.python.org/pep-0008/#class-names)). |
| Account hierarchy uses **single-table inheritance** rather than separate tables | [account.py](app/models/account.py) | The two subclasses share every column from the abstract base; STI keeps the model count low and lets us query the parent type while still getting the concrete subclass instance back. Joined-table inheritance would add a join on every account lookup with no behavioural benefit. |
| `UserCredentials` is its **own table** (1:1 composition) rather than columns on `Account` | [credentials.py](app/models/credentials.py) | The SRS data-hiding heuristic (§4.1.2) is materialised in the schema: routers querying `Account` cannot see the password hash unless they explicitly request the relationship. This makes accidental leaks much harder. |
| `Resource` keeps a single `content_type` string instead of subclasses | SRS §2.2.2 already justifies the collapse | Subclasses would share all responsibilities — no behavioural divergence. |
| Quiz questions stored as JSON column | [quiz.py](app/models/quiz.py) | SRS §2.2.3 collapses `QuizQuestion`. JSONB is the natural representation and avoids a child table whose only purpose is an ordering column. |
| `Feedback.target` is a polymorphic FK (`target_type` + `target_id`) | [feedback.py](app/models/feedback.py) | The UML shows `Feedback targets FirstAidGuidance, Resource`. A polymorphic key is the smallest correct realisation; alternatives would either duplicate the table or add a join across an "anything" table. The downside (no FK constraint to either target table) is accepted because writes are gated through Pydantic + the router. |
| `Donation.amount` stored as `amount_cents` (integer) | [donation.py](app/models/donation.py) | SRS §1.3.2 boundary case requires numeric validation. Integers cents are immune to floating-point rounding errors — critical for any monetary value. |
| Five-failures lockout + lockout timestamp moved onto `UserCredentials` | [credentials.py](app/models/credentials.py), [auth_manager.py](app/domain/auth_manager.py) | The SRS specifies the rule but not where the counter lives. Putting it on the data-holder keeps `AuthManager` stateless across instances and makes the rule survive process restarts. |
| Domain exceptions translated to HTTP via a single FastAPI handler | [main.py](app/main.py) | Routers raise `InvalidInputException`, `InvalidCredentialsException`, etc. The handler produces a stable JSON shape `{code, detail, field?, retry_after_seconds?}`. Routers never catch domain exceptions or build HTTPException directly — this removes a huge class of "forgot to handle" bugs. |
| **Bootstrap order matches SRS §6** | [main.py](app/main.py) | FastAPI lifespan callback eagerly instantiates `AppController`, which in turn creates `AuthManager` and the `EventBus`. Dashboard classes are instantiated on demand per request via `AppController.create_dashboard`. This matches "On-Demand Class Instantiation" (SRS §6.5). |

Nothing in the SRS UML was discarded.

---

## 5. Discussion of the Assignment 2 design — quality review

### Good aspects

- **Layering** (Controller / Support / Entity / Data-holder) made the implementation almost mechanical — every class had an obvious home.
- **CRC cards** for each candidate class meant collaborators were already inventoried; we never had to invent "who calls whom" during coding.
- **Pattern selection** is appropriate: the chosen five patterns are exactly the ones the code naturally wants once you start writing it (no pattern-fitting).
- **Heuristics explicitly named** gave concrete review criteria for each PR.

### Aspects missing from / weak in the original design

- **No timestamp/audit fields** on entities. We added `created_at` / `updated_at` via a `TimestampMixin`; without these the dashboard cannot order anything chronologically.
- **No explicit data type for monetary amounts**. The Assignment 2 design says "donation amount" without a unit; we chose integer cents in code (see §4 above) and the SRS would benefit from saying so.
- **`Account` discriminator absent**. The UML shows the inheritance but doesn't say how persistence distinguishes the two subclasses. We made it a single-table `role` column.
- **Polymorphic `Feedback.target` not specified**. The UML draws `Feedback targets ResourceOrGuidance` but doesn't say how. We chose a (`target_type`, `target_id`) tuple; the SRS should specify this explicitly.
- **No clarity on `FirstAidGuidance ↔ Resource` cardinality**. The UML reads "supported by" which we made M:N via a link table (`first_aid_resource_link`). A guidance often references several supporting media items, and a single media item (e.g. a "vital signs" video) supports several guidance procedures.
- **No password / credential rotation flow**. Out of A3 scope but worth flagging for A4.

### Errors / flaws

- **Class name `FirstAidguidance`** (lowercase 'g') in the SRS contradicts SRS §1.3.1's stated PascalCase convention. We renamed to `FirstAidGuidance`.
- **Composition between `Donation` and `DonationRecord`** in the UML uses an open diamond in places — this should be a *filled* (composition) diamond per SRS §4.1.7. Code enforces composition unambiguously via `cascade="all, delete-orphan"`.
- **`Feedback` and `FeedbackEntry`** are drawn with two separate "manages CRUD" labels in the UML; only one is necessary because composition implies lifecycle ownership.

### Level of interpretation required

- **Medium.** The CRC cards are detailed enough to map directly to method names, but the UML diagram itself is small and arrow labels are sometimes ambiguous ("supports" vs "supported by"). We resolved every ambiguity by re-reading the CRC text in SRS §3.3 and choosing the interpretation that placed responsibility on the entity owning the data (heuristic 4.1.4).

---

## 6. Lessons learnt

1. **Specify cardinalities, not just associations.** "Resource supports FirstAidGuidance" doesn't tell the implementer whether to build a join table or a single FK. A2-style UML diagrams should mark `1`, `0..*` etc. on every line.
2. **Choose representations for primitive concepts during design, not coding.** Monetary amounts, timestamps, identifiers — leaving these to "the implementer" defers the same decision to every developer who later reads the schema.
3. **Heuristics are easier to enforce when they appear in code review checklists** rather than only in the design document. We codify them in this DESIGN.md so a reviewer can grep for each heuristic against a diff.
4. **The Singleton + Factory + Template Method combination is overpowered for small apps**, but it pays off the first time you swap one of the participants (a different payment provider, a different dashboard variant). The cost is low because the patterns express what the SRS already says about roles.
5. **Separate the data-holder tables physically**, not just conceptually. Putting `UserCredentials` in its own table made data-hiding the path of least resistance.

---

## 7. Coding standard

| Concern | Reference |
| --- | --- |
| Python style | [PEP 8](https://peps.python.org/pep-0008/) — enforced by `ruff` (`pyproject.toml`) with `E, F, I, UP, B, SIM` rule sets. |
| Python docstrings | [PEP 257](https://peps.python.org/pep-0257/) — every public class and function has a triple-double-quoted docstring. |
| Type hints | [PEP 484](https://peps.python.org/pep-0484/) + PEP 604 union syntax (`X | None`). |
| Imports | Sorted by `ruff` (isort-compatible). Standard library → third-party → first-party. |
| Identifier conventions | Class names: PascalCase. Functions / variables: snake_case. Constants: UPPER_SNAKE_CASE. Private helpers: `_underscore` prefix. |
| Exception design | All domain failures inherit from `PetAidError`. A single FastAPI handler renders them to JSON. |
| FastAPI conventions | Routers are thin; business logic lives in `app/domain/` or on entity methods. Pydantic v2 models in `app/schemas/`. |

Linting locally: `ruff check app` and `ruff format app`.

---

## 8. Verification scenarios → code paths

| SRS § | Scenario | Touched files |
| --- | --- | --- |
| 7.1 | Emergency First Aid | `app/api/v1/first_aid.py`, `app/domain/dashboards.py` |
| 7.2 | Inquiry + response | `app/api/v1/inquiries.py`, `app/models/inquiry.py` (state machine) |
| 7.3 | Resource approval | `app/api/v1/resources.py`, `app/domain/media_storage.py` |
| 7.4 | Quiz + score | `app/api/v1/quizzes.py`, `app/models/quiz.py` (`Quiz.evaluate`) |
| 7.5 | Donation | `app/api/v1/donations.py`, `app/domain/payment_processor.py`, `app/models/donation.py` |
| 7.6 | Chat session | `app/api/v1/chats.py`, `app/models/chat.py` |
| 7.7 | Feedback | `app/api/v1/feedback.py`, `app/models/feedback.py` |
| 7.8 | Registration | `app/api/v1/auth.py`, `app/domain/auth_manager.py` |

All eight are reachable from the seeded demo data — `python -m app.seed` populates Alwin (Pet Owner) and Dr. Kavitha (Vet Expert, MFA `123456`).
