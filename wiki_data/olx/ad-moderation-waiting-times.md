---
title: "Ad Moderation & Waiting Times"
confluence_id: "60651012507"
confluence_url: "https://naspersclassifieds.atlassian.net/wiki/spaces/OCP/pages/60651012507"
synced: "2026-07-25"
product: "olx"
---

Table of Contents — Ad Moderation & Waiting Times

# Overview

This article covers three moderation scenarios that CS agents may encounter after an ad is submitted on OLX:

* **Waiting time for approval** — The ad is pending moderation (quality control review) and the user is asking why it has not gone live yet.
* **Pro user ad moderated without an account manager** — A professional user's ad has been moderated and no account manager is assigned to escalate the case.
* **Ad blocked due to email domain** — The ad is rejected because OLX blocks publishing from certain email domains as a security measure against fraud.

In all three cases, agents must verify the moderation reason in NEO or Atlas, communicate clearly with the user, and follow the appropriate resolution steps outlined in the Procedures section below.

---

# Definitions

**Moderated Ad:** An ad that has been placed under review or rejected by OLX's moderation system (automated or manual). The ad will not be visible on the site until the issue is resolved or the ad is reactivated.

**Waiting Time:** The period between an ad being submitted by the user and it becoming publicly visible. OLX randomly selects a group of ads for quality control, which can create a delay. During high-volume publishing periods, this waiting time may be longer than usual.

**Email Domain Block:** A security mechanism whereby OLX prevents ads from being published when the user's account email belongs to a domain that has been flagged as high-risk for fraud (e.g., domains that allow easy creation of fake accounts).

**Q&S Team (Quality & Safety):** The internal team responsible for managing moderation rules, reviewing blocked email domains, and handling fraud-related escalations. CS agents contact this team via Slack (fraud_reports channel) when a user account requires deeper analysis.

**Atlas:** OLX's internal admin tool used by CS agents to view and manage user accounts and ads. Agents can reactivate ads, add account notes, and perform administrative actions directly in Atlas.

**NEO:** OLX's moderation and content management system. NEO displays the moderation reason for an ad and provides access to filters such as Blocked Email Domains. Agents use NEO to diagnose why an ad was moderated and to look up which email domains are on the blocklist.

**Pro User (Professional User):** A business or professional account holder on OLX, typically with a paid package. Pro users may have an assigned account manager (Sales agent) for escalations; when no account manager is assigned, moderation issues are handled directly by the CS team.

**Account Manager:** A Sales agent assigned to a professional user's account. When a pro user has an account manager, moderation escalations should be coordinated with them. When no account manager is assigned (sem gestor), the CS agent handles the case independently.

---

# Procedures

## 1. Ad Waiting for Approval — Waiting Time

**Situation:** The user contacts CS saying they published an ad but it is not yet live because it is pending moderation.

Analysis steps:

1. **Check for technical issues:** Verify in Atlas / NEO whether there is a known technical problem keeping the ad in a pending state. If a bug is identified, report it to the relevant team.
2. **Activate the ad if possible:** If the ad is technically fine and there is no compliance issue, manually activate it for the user via Atlas.
3. **Explain the moderation process:** Inform the user that OLX randomly selects a group of ads for quality control purposes. This is a normal part of the platform's operation.
4. **Manage expectations:** Communicate that OLX strives to provide a seamless service, but during high-volume publishing periods, the waiting time may be longer than usual.

**Communication to the user (suggested message):**

"Your Ad is active since…. (link). OLX randomly selects a group of ads for quality control purposes. We strive to provide a seamless service, however during periods of high ad volume, waiting times may be longer than usual. We apologise for any inconvenience."

## 2. Ad Moderated — Pro User Without Account Manager

**Situation:** A professional user's ad has been moderated (removed or rejected) and the account does not have an assigned account manager (gestor de conta). The CS agent handles the case directly.

Resolution steps:

1. **Confirm whether the user has an account manager:** Check the user's account in Atlas. If no account manager is assigned, proceed independently. If yes, add the Account manager to the email CC.
2. **Check the moderation reason:** Access NEO or Atlas and review the moderation template applied to the ad. Identify the specific reason the ad was moderated.
3. **Analyse the account:** Review the user's history. If the account appears legitimate and there are no signs of fraud or repeated violations, proceed with reactivation.
4. **Reactivate the ad if appropriate:** If the moderation was an error or the user has corrected the issue, reactivate the ad via Atlas.
5. **Escalate to Q&S if needed:** If there are fraud indicators or the case is complex, report via the Slack #fraud_reports channel for Q&S team analysis.
6. **Leave a note in NEO:** Document the actions taken, including the moderation reason and any communications with the user or Q&S team.
7. **Communicate with the user:** Inform the user of the moderation reason, what steps have been taken, and what action (if any) is required on their side.

## 3. Ad Blocked Due to Email Domain

**Situation:** For security reasons, OLX blocks ad publishing from certain email domains. This occurs because certain domains make it too easy to create fraudulent accounts. The user contacts CS saying their ad cannot be published.

How to check — NEO has two key points to look at:

**1. Check the moderation reason on the ad:**

* In NEO, open the ad in question. The moderation/rejection reason will reference "email domain".

**2. Check NEO's Blocked Email Domains filter:**

1. In NEO, click on the arrow next to the NEO menu and select **Blocked Email Domains**.
2. Search for the user's email domain.
3. If the domain removal is justified (e.g., it was blocked incorrectly or the user is legitimate), request an analysis from the Q&S team to remove the domain from the blocklist.

Information to communicate to the user:


* Inform the user that, for security reasons, OLX does not accept ad publishing from accounts whose email domain is on the blocklist (e.g., @example.com — use the actual domain found in NEO).
* Suggest that the user change the email address on their OLX account. After the email change, they will be able to publish new ads.
* Explain the email change process step by step.
* Reset the ad placement counter and/or offer to reactivate the user's ads after the email change (customer-centric action).

**Important:** Do NOT reactivate the user's ads without them first changing their email address. The system is designed to block those ads again automatically if the email domain remains on the blocklist.

Leave a note in the Salesforce ticket identifying the account ID. This is important to preserve the data in case the user changes their email address.


---


# FAQs

**Q: The user says their ad was published but it is not visible on the site. What should I check first?**

A: Check the ad status in Atlas/NEO. If it is "pending moderation", explain to the user that OLX randomly selects ads for quality control. If there is a technical issue keeping it pending, report it to the relevant team and activate the ad manually if possible.

**Q: How long does the moderation waiting time usually take?**
A: The waiting time varies. During peak publishing periods it may take longer than usual. There is no fixed SLA to communicate to the user, but agents should manage expectations by explaining that OLX strives to minimise delays.

**Q: A pro user's ad was moderated and they don't have an account manager. Can I simply reactivate it?**
A: Only if the moderation appears to have been an error and the account shows no fraud indicators. Review the moderation reason in NEO/Atlas first. If there are any signs of fraud or if you are unsure, escalate to the Q&S team via Slack (#fraud_reports) before taking any action. Always leave a note in Admin.

**Q: The user says their email domain is blocked, but they are a legitimate user. What do we do?**
A: Verify in NEO > Blocked Email Domains that the domain is indeed on the blocklist. If the user appears legitimate and you believe the domain block may be unjustified, request an analysis from the Q&S team to review and potentially remove the domain. In the meantime, advise the user to change their OLX account email to an unblocked domain.

**Q: Can I reactivate a user's ads before they change their blocked email domain?**
A: No. Reactivating ads without the user first changing their email is not effective — the system will automatically block the ads again. The email change must happen first.

**Q: What information should I note in Salesforce when handling an email domain block case?**
A: Leave a note on the Salesforce ticket with the user's account ID. This is crucial to retain account data in case the user changes their email (which creates a new account context).