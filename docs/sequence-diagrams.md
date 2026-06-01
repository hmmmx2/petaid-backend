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
