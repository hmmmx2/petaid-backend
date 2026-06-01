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
