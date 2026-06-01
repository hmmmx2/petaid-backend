# PetAid Revised Sequence Diagrams

This file collects sequence diagrams that the as built code follows in a way that differs from the original. Each section shows the revised PlantUML and a short reason for the change. The file grows as more diagrams are revised.

---

## 7.2 Pet Owner Submits an Inquiry and Receives a Response

```plantuml
@startuml SequenceDiagram-7.2-Revised
title 7.2 Pet Owner Submits an Inquiry and Receives a Response (as built)

actor "Pet Owner" as Owner
participant ":PetOwnerDashboard" as PD
participant ":AppController" as AC
participant ":EventBus" as EB
participant ":Inquiry" as I
participant ":VetDashboard" as VD
actor "Veterinary Expert" as Vet

== Submission Phase ==
Owner -> PD : submitInquiry(question, images)
PD -> I : create(owner, question, images, status=PENDING)
I --> PD : inquiry
PD -> AC : publish(CH_INQUIRY_SUBMITTED, inquiryId)
AC -> EB : forward event
note over EB
  Pool model. The inquiry stays PENDING.
  Every available veterinary expert can see
  it in their pending list. No eager
  assignment to one person.
end note
PD --> Owner : showSubmissionConfirmed()

== Review and Response Phase ==
Vet -> VD : openInquiry(inquiryId)
note right of VD
  Inquiry details are preloaded with the
  dashboard snapshot, so no extra fetch.
end note
VD --> Vet : displayFullInquiry()
Vet -> VD : postResponse(responseText)
VD -> I : respond(vetId, responseText)
note over I
  Claim and lock. The first vet to reply
  takes the inquiry by setting
  assigned_vet_id. Any later vet who
  tries gets a 403.
end note
I -> I : assigned_vet_id = vetId
I -> I : status = RESPONDED
I --> VD : updated inquiry
VD -> AC : publish(CH_INQUIRY_RESPONDED, inquiryId)
AC -> EB : forward event
VD --> Vet : showResponseSent()

== Retrieval Phase ==
Owner -> PD : openInquiry(inquiryId)
note right of PD
  Owner refreshes or revisits the
  inquiries panel. The updated inquiry
  arrives with the next snapshot load.
end note
PD --> Owner : displayResponse()
@enduml
```

### Why the change

The original 7.2 diagram routes a new inquiry to one chosen veterinary expert at the moment of submission. The as built code uses a pool model instead. Every available expert sees the pending inquiry, and the first one who replies claims it. A claim and lock check then prevents any other expert from overwriting that reply. This closes a real authorisation gap and balances the load across the team without extra routing logic. The AppController publishes inquiry events through the EventBus. Real time push to the Pet Owner is left out on purpose because the SRS treats inquiry as an asynchronous channel.

---

## 7.3 Veterinary Expert Publishes a New Resource

```plantuml
@startuml SequenceDiagram-7.3-Revised
title 7.3 Veterinary Expert Publishes a New Resource (as built)

actor "Veterinary Expert" as Vet
participant ":VetDashboard" as VD
participant ":MediaStorage" as MS
participant ":Resource" as R

== Creation Phase ==
Vet -> VD : openNewResourceForm()
VD --> Vet : showResourceForm()
Vet -> VD : submit(title, contentType, petTypeId, mediaPath, sizeBytes)
VD -> MS : accept(contentType, mediaPath, sizeBytes)
note over MS
  Validate the file format and size against
  the boundary rules in the SRS. Reject early
  if it fails so no row hits the database.
end note
MS --> VD : descriptor
VD -> R : create(title, contentType, petTypeId, author=vet, mediaPath, status=DRAFT)
R --> VD : resource
VD --> Vet : showDraftSaved()
note right of VD
  The whole creation happens in one
  transactional call. Either the resource
  exists fully formed or it never exists.
end note

== Publication Phase ==
Vet -> VD : reviewDraft(resourceId)
note right of VD
  Draft details are already in the resource
  list, so no extra fetch is needed.
end note
VD --> Vet : displayDraft()
Vet -> VD : publish(resourceId)
VD -> R : status = PUBLISHED
R --> VD : updated resource
VD --> Vet : showPublicationConfirmed()
@enduml
```

### Why the change

The original 7.3 diagram splits resource creation into many small steps. It expects an empty draft to be created up front, then media uploaded, then pet type linked, then guidance linked, then publication. The as built code uses a single atomic create call followed by a separate publish call. MediaStorage validates the file metadata inline during create, so the resource is either saved fully formed or not at all. The pet type is a required column on the resource and is set during create, not as a later link step. Publication is the only state change after creation, moving the status from DRAFT to PUBLISHED. Runtime linking of a resource to a FirstAidGuidance is not implemented as a separate function in this flow.

---

## 7.4 Pet Owner Completes a Quiz Linked to a Resource

```plantuml
@startuml SequenceDiagram-7.4-Revised
title 7.4 Pet Owner Completes a Quiz Linked to a Resource (as built)

actor "Pet Owner" as Owner
participant ":PetOwnerDashboard" as PD
participant ":Quiz" as Q
participant ":QuizAttempt" as QA

== Topic Selection Phase ==
Owner -> PD : openQuizzesTab()
note right of PD
  The quiz list is preloaded with the
  dashboard snapshot, so no separate
  fetch by pet type is needed at runtime.
end note
PD --> Owner : displayQuizList()

== Quiz Attempt Phase ==
Owner -> PD : selectQuiz(quizId)
PD --> Owner : displayAllQuestions(quiz)
note right of PD
  All questions render in one form. The
  owner fills every answer locally before
  submitting, which keeps round trips low
  and the correct answers hidden until
  the attempt is complete.
end note
loop For each question in the form
  Owner -> PD : pickAnswer(index)
end

== Result and Persistence Phase ==
Owner -> PD : submitQuiz(answers)
PD -> Q : evaluate(answers)
note over Q
  The Quiz computes score, pass or fail,
  and a per question report in one batch.
  This protects the best score retention
  rule because correct answers are never
  revealed during the attempt.
end note
Q --> PD : (score, passed, perQuestion)
PD -> QA : create(petOwnerId, quizId, score, passed, answers, completedAt)
QA --> PD : attempt
PD --> Owner : displayResultAndProgress()
@enduml
```

### Why the change

The original 7.4 diagram has the owner pick answers one at a time, with the software evaluating each answer during the attempt and revealing the correct one before the quiz ends. The as built code uses batch evaluation. The owner answers every question in a single form, then a single submit call sends all answers, the Quiz computes score and per question feedback in one pass, and the result is persisted as a QuizAttempt. This keeps the highest score retention rule honest, because correct answers are never visible while the attempt is in progress, and it removes the extra round trips between the owner and the software for each question. The list of quizzes also comes preloaded with the dashboard snapshot rather than a runtime pet type lookup.

---

## 7.5 Pet Owner Makes a Donation

```plantuml
@startuml SequenceDiagram-7.5-Revised
title 7.5 Pet Owner Makes a Donation (as built)

actor "Pet Owner" as Owner
participant ":PetOwnerDashboard" as PD
participant ":Donation" as D
participant ":PaymentProcessor" as PP
participant ":DonationRecord" as DR
participant ":VetDashboard" as VD
actor "Veterinary Expert" as Vet

== Donation Initiation Phase ==
Owner -> PD : openDonationFunction()
PD --> Owner : displayDonationForm()
Owner -> PD : submitDonation(amount, paymentMethod)
PD -> D : create(amount, paymentMethod, status=PENDING)

== Payment Processing Phase ==
D -> PP : charge(amount, currency)
note over PP
  Adapter pattern. MockPaymentProcessor in
  demo mode, FailingPaymentProcessor used
  in tests to exercise the failure path.
end note
alt Successful payment
  PP --> D : transactionRef
  D -> DR : create(transactionRef, amount, processed_at, final_status)
  DR --> D : record
  D -> D : mark_succeeded(record)
  note right of D
    The mark_succeeded method on Donation
    enforces the invariant that SUCCEEDED
    implies a record exists. The DonationRecord
    is then locked at the data layer by a
    before_update listener so it cannot be
    changed after creation.
  end note
  D --> PD : donation, record
  PD --> Owner : showDonationReceipt()
else Payment failure
  PP --> D : PaymentFailedException
  D -> D : mark_failed()
  D --> PD : error
  PD --> Owner : showFailureMessageWithRetry()
end

== Donation Review Phase ==
Vet -> VD : openDonationReview()
VD -> D : listSucceededDonations()
note right of VD
  Donations come back with their records
  embedded through eager loading, so no
  separate read call is needed.
end note
D --> VD : donations
VD --> Vet : displayDonationDetails()
@enduml
```

### Why the change

The original 7.5 diagram and the as built code line up closely already. Both use the Adapter pattern through PaymentProcessor, both create the immutable DonationRecord through composition only on success, and both handle the failure path with a clear status. The small adjustments needed to follow the diagram fully were made in code rather than in the drawing. Donation now exposes mark_succeeded and mark_failed methods so the status transition lives on the entity instead of in the router, the payment method label is now carried through from the form to the donation row, and DonationRecord is protected by a before_update listener that refuses any change after insert. With those in place the diagram and the software describe the same flow.

---

## 7.6 Pet Owner and Veterinary Expert Engage in a Chat Session

```plantuml
@startuml SequenceDiagram-7.6-Revised
title 7.6 Pet Owner and Veterinary Expert Engage in a Chat Session (as built)

actor "Pet Owner" as Owner
participant ":PetOwnerDashboard" as PD
participant ":Chat" as C
participant ":ConnectionManager" as CM
participant ":VetDashboard" as VD
actor "Veterinary Expert" as Vet

== Initiation Phase ==
Owner -> PD : startChat(subject, vetId optional)
PD -> C : create(petOwnerId, vetId, subject, status=INITIATED)
C --> PD : chat
PD -> CM : broadcast(chat_new)
note over CM
  If a specific vet was chosen the alert
  goes to that vet. Otherwise the chat
  enters a shared pool and the alert goes
  to every active veterinary expert.
end note
CM --> VD : chat_new
VD --> Vet : showIncomingChatAlert()

== Active Conversation Phase ==
Vet -> VD : joinChat(chatId)
VD -> C : join(vet)
note over C
  The join sets vet_id and flips the status
  to ACTIVE. The first vet to join claims
  a pool chat, which is the same claim and
  lock pattern used for inquiries.
end note
C --> VD : updated chat
VD -> CM : broadcast(chat_update, status=ACTIVE)
CM --> PD : chat_update
PD --> Owner : displayExpertOnline()

loop Real-time message exchange (either direction)
  alt Pet Owner sends
    Owner -> PD : sendMessage(text)
    PD -> C : appendMessage(petOwner, text)
    C --> PD : message
    PD -> CM : broadcast(message)
    CM --> VD : message
    VD --> Vet : displayMessage()
  else Veterinary Expert sends
    Vet -> VD : sendMessage(text)
    VD -> C : appendMessage(vet, text)
    C --> VD : message
    VD -> CM : broadcast(message)
    CM --> PD : message
    PD --> Owner : displayMessage()
  end
end

== Closure Phase ==
alt Either actor closes
  Owner -> PD : closeChat()
  PD -> C : close()
  C --> PD : updated chat
else
  Vet -> VD : closeChat()
  VD -> C : close()
  C --> VD : updated chat
end
note over C
  Status flips to CLOSED. The message
  history stays in the chat_messages table
  for future reference, so no separate
  archive step is needed.
end note
C -> CM : broadcast(chat_update, status=CLOSED)
CM --> PD : chat_update
CM --> VD : chat_update
PD --> Owner : showChatClosed()
VD --> Vet : showChatClosed()
@enduml
```

### Why the change

The original 7.6 diagram routes a new chat to one chosen veterinary expert at creation. The as built code uses a pool model. When the owner picks a specific expert the chat goes directly to that person, otherwise it enters a shared pool and the alert reaches every active expert through the ConnectionManager. The first expert to join claims the chat, flips the status to ACTIVE, and from that point messages flow in both directions through the WebSocket Observer layer. Either actor may close the chat, which flips the status to CLOSED and broadcasts to both sides. The diagram shows an archiveMessageHistory self call but the code keeps history in place by leaving the chat_messages rows after closure, which retains the conversation for future reference without a separate archive store.

---

## 7.7 Pet Owner Submits Feedback on Published Content

```plantuml
@startuml SequenceDiagram-7.7-Revised
title 7.7 Pet Owner Submits Feedback on Published Content (as built)

actor "Pet Owner" as Owner
participant ":PetOwnerDashboard" as PD
participant ":Feedback" as F
participant ":FeedbackEntry" as FE
participant ":ConnectionManager" as CM
participant ":VetDashboard" as VD
actor "Veterinary Expert" as Vet

== Submission Phase ==
Owner -> PD : openFeedbackForm(resourceId)
PD --> Owner : displayFeedbackForm()
Owner -> PD : submitFeedback(rating, comment, flagInaccurate)
PD -> F : create(submitterId, resourceId, flagged)
F -> FE : create(rating, comment)
note over F
  The whole submission happens in one
  atomic call. Feedback targets a single
  Resource through a real foreign key,
  matching the class diagram.
end note
FE --> F : entry
F --> PD : feedback
PD --> Owner : showSubmissionConfirmed()

== Flag Routing Phase ==
alt Feedback flagged as inaccurate
  PD -> CM : broadcast(feedback_flagged)
  note right of CM
    Mirrors the chat pool alert. The push
    reaches every active veterinary expert
    in real time through the ConnectionManager.
  end note
  CM --> VD : feedback_flagged
  VD --> Vet : showFlaggedFeedbackAlert()
end

== Veterinary Expert Review Phase ==
Vet -> VD : openFeedbackPanel()
note right of VD
  Flagged feedback rows arrive preloaded
  with the rating, comment, and the linked
  resource title resolved from the snapshot.
  A view resource link jumps the vet to
  the resources tab for full context.
end note
VD --> Vet : displayFlaggedContentForReview()
@enduml
```

### Why the change

The original 7.7 diagram has an alt branch where feedback targets either a FirstAidguidance or a Resource. That conflicts with the class diagram, which shows Feedback targeting a Resource only. The as built code follows the class diagram, so feedback uses a single resource_id foreign key and the alt branch is gone. The submission also happens in one atomic call rather than separate create and assignTarget steps, which keeps the data consistent. The flag routing path is now wired end to end. The router publishes the event on the EventBus and also broadcasts a real time alert through the ConnectionManager to every active veterinary expert, mirroring the chat pool model. The vet panel shows the flagged feedback with the linked resource title resolved from the snapshot, plus a small link that opens the resources tab for full context.

---

## 7.8 Pet Owner Registers an Account with Email Verification

```plantuml
@startuml SequenceDiagram-7.8-Revised
title 7.8 Pet Owner Registers an Account with Email Verification (as built)

actor "Pet Owner" as Owner
participant ":AppController" as AC
participant ":AuthManager" as AM
participant ":PetOwner" as PO
participant ":UserCredentials" as UC
participant ":PetOwnerDashboard" as PD

== Registration Submission Phase ==
Owner -> AC : submitRegistration(email, password, role=pet_owner, fullName)
note over AC
  AppController is the backend composition
  root that owns AuthManager. The Pet Owner
  reaches it through the Welcome screen and
  the REST API rather than calling methods
  on AppController directly.
end note
AC -> AM : register(email, password, role, fullName)

alt Input format valid and role is pet_owner
  == Account Creation Phase ==
  AM -> PO : _make_account(role, fullName)  [Factory Method]
  note right of AM
    Only pet_owner may self register. A vet
    role is rejected here so a caller cannot
    obtain a vet token through the email
    verification path.
  end note
  PO --> AM : account
  AM -> UC : create(account_id, email, bcrypt(password))
  UC --> AM : credentials
  note over UC
    Composition through a unique foreign key
    with cascade. The credentials cannot
    outlive the account.
  end note

  == Email Verification Phase ==
  AM -> AM : generateVerificationCode()
  note right of AM
    The code is a six digit value with a
    fifteen minute time to live. It lives in
    AuthManager memory rather than on the
    UserCredentials row, which keeps the
    sensitive short lived value out of the
    database.
  end note
  AM --> AC : (account, code)
  AC --> Owner : promptVerificationCode()
  Owner -> AC : submitVerificationCode(email, code)
  AC -> AM : verify_email(email, code)
  AM -> AM : matchCode(email, code)
  alt Verification code correct
    AM -> UC : set email_verified to true
    AM --> AC : tokenPair
    AC --> Owner : registrationConfirmed()

    == Dashboard Activation Phase ==
    Owner -> AC : openDashboard(token)
    AC -> AC : create_dashboard(account)  [Factory Method]
    AC -> PD : render()  [Template Method]
    note right of PD
      Dashboard.render is the Template Method
      that calls the subclass _panels
      implementation to assemble the snapshot.
    end note
    PD --> AC : snapshot
    AC --> Owner : displayPetOwnerDashboard()
  else Verification code incorrect
    AM --> AC : InvalidInputException(code)
    AC --> Owner : showVerificationErrorAndRetry()
  end
else Input format invalid
  AM --> AC : InvalidInputException(field)
  AC --> Owner : showFieldErrorMessage()
end
@enduml
```

### Why the change

The original 7.8 diagram has the user talk directly to AppController and shows UserCredentials generating the verification code. The as built code follows the same shape with two small adaptations. AppController is the backend composition root that owns AuthManager, and the Pet Owner reaches it through the Welcome screen and the REST API rather than by calling AppController methods directly. The verification code lives in AuthManager memory with a fifteen minute time to live rather than on a UserCredentials column, which keeps the sensitive short lived value out of the database. The Factory Method on AuthManager and the Template Method on Dashboard.render are realised exactly as drawn. Only pet_owner may self register, so a vet token cannot be obtained through the verification path.

---
