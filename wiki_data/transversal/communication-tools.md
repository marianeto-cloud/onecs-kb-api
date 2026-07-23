---
title: "Communication Tools"
confluence_id: "60741976101"
confluence_url: "https://naspersclassifieds.atlassian.net/wiki/spaces/OCP/pages/60741976101"
synced: "2026-07-25"
product: "transversal"
---

put / link to the article

# Overview

Salesforce offers several built-in communication tools that help Customer Service agents collaborate, take notes, use templates, and interact with customers. This article covers five key tools: Chatter, Notes, Quick Text, Chat (Omni-Channel), and Email Signature.


These tools allow agents to: communicate with colleagues on cases, store internal notes, reuse canned responses, chat with customers in real time, and manage professional email signatures.


---

# Chatter

Chatter is the collaboration channel for Salesforce users. It is the main tool for communicating with other agents and team members directly within cases.


## 1. Email

The Email section shows the response that is sent to the customer.

## 2. Post

Post allows you to send internal chat notifications via Salesforce. You can mention colleagues, sales teams, etc using @ to get their attention on a case.

Example 1: To ask your Team Leader for help on a case, post a comment mentioning @name.surname with your question.

Example 2: To request help from someone in another Business Unit: first add the person to the case team (Add Member > search for the name > Save), then mention them in the post.


## 3. Task

You can create a task for another person to resolve, keeping the case on hold until you receive a response.

## 4. Fields Shortcut

Fields Shortcut shows all the fields that must be filled in to close the case. These include Root Causes, Posting Category, Customer Type, Status, and Remove CSAT.

---

# Notes

Notes in Salesforce are the equivalent of Internal Notes in Zendesk. However, Notes in Salesforce can be connected to any record — not just a Case.


---

# Quick Text

Quick Text is the Salesforce alternative to Macros in Zendesk. It allows agents to insert pre-written text snippets directly into cases, chats, or emails.

---

# Chat (Omni-Channel)


Chat is integrated directly into Omni-Channel, Salesforce's routing and workload management system. It allows agents to handle customer conversations in real time.


## 1. Going Online

To be available for chat in Omni-Channel, you have two options:
* Available Chat — use this option (recommended)
* Available Email & Chat — receives both emails and chats

## 2. Accepting and Managing Chats

* Accept the chat by clicking the checkmark in Omni-Channel
* The chat page opens and shows the conversation with the customer
* Click End Chat to close the conversation with the customer (the case still needs to be closed separately)
* For each chat, a Case is automatically created and assigned to the Chat Guuru Hot Transfers queue — it must be closed as Solved

## 3. Current Limitations

* Customers cannot send images directly — they must click Request a File to authorize sharing for each image
* Agents cannot send attachments or images to users. Workaround: use the Google Awesome Screenshot extension
* Each chat opens a case that must be manually closed

## 4. Google Awesome Screenshot

Google Awesome Screenshot is a browser extension that allows agents to capture and share screenshots directly with customers.
Extension link: https://www.awesomescreenshot.com/

---

# Email Signature

The email signature in Salesforce is automatically populated using merge fields and follows the company standard for all outbound customer emails.

## 1. Merge Fields to Use


Paste the following merge fields in the Email Signature field in Salesforce:

* {{{Sender.FirstName}}} {{{Sender.LastName}}}
* {{{Sender.Email_Signature__c}}}

## 2. How to Configure

To configure your email signature in Salesforce, go to your user profile settings and fill in the Email_Signature__c custom field with your preferred signature text.