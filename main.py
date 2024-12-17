"""
This code is provided on an as-is warranty-free basis by Joseph Winkie <jjj333.p.1325@gmail.com>

This code is licensed under the A-GPL 3.0 license found both in the "LICENSE" file of the root of this repository
as well as https://www.gnu.org/licenses/agpl-3.0.en.html. Read it to know your rights.

A complete copy of this codebase as well as runtime instructions can be found at
https://github.com/jjj333-p/email-llama/
"""
import base64
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import imaplib
import email
from time import sleep
from ollama import chat
from ollama import ChatResponse
import mailparser

# directory to store message history
if not os.path.exists('./db/'):
    os.mkdir('./db/')

# Email details
with open("login.json", "r") as file:
    login = json.load(file)

run: int = 0

while True:
    print("run", run)
    run += 1

    try:
        # Connect to the server
        mail = imaplib.IMAP4_SSL(login["imap_addr"], login["imap_port"])
        mail.login(login["email"].split("@")[0], login["password"])

        # Select the mailbox you want to use
        mail.select("INBOX")

        # Search for new emails
        status, messages = mail.search(None, "UNSEEN")
        email_ids = messages[0].split()

        # fetch email ids we just searched for
        for num in email_ids:
            typ, data = mail.fetch(num, '(RFC822)')

            # no idea why a message id returns a list but okay
            for response in data:

                # everything does this, i have no idea
                if isinstance(response, tuple):
                    msg = mailparser.parse_from_bytes(response[1])

                    # sanity checks
                    if len(msg.from_) < 1 or len(msg.from_[0]) < 12:
                        continue

                    # parse in details
                    sender: str = msg.from_[0][1]
                    subject: str = msg.subject if msg.subject else "No subject"
                    body_lines: list[str] = []

                    # rid of the replies, rely on stored content for that
                    for line in msg.text_plain[0].splitlines():
                        if login["email"].split("@")[0] in line or login["displayname"] in line or line.startswith(
                                "> "):
                            break
                        else:
                            body_lines.append(line)

                    body: str = "\r\n".join(body_lines)

                    print("From:", sender)
                    print("Subject:", subject)
                    print("Body:", body)

                    subject_by_words: list[str] = subject.split()

                    # messages will be stored by base64 hash of subject
                    if subject_by_words[0] == "Re:" or subject_by_words[0] == "re:" or subject_by_words[0] == "RE:":
                        del subject_by_words[0]
                    encoded: str = base64.urlsafe_b64encode(
                        f'{sender} {" ".join(subject_by_words)}'.encode()).decode()

                    # attempt to parse out what model to use
                    model: str = login["default_model"]
                    default_model: bool = True
                    if subject_by_words[0] in login["permitted_models"]:
                        model = subject_by_words[0]
                        default_model = False
                        del subject_by_words[0]

                    system_prompt: dict[str, str] = {
                        "role": "system",
                        "content": " ".join(subject_by_words),
                    }
                    history: list[dict[str, str]] = [system_prompt]

                    # read in history from disk
                    if os.path.exists(f'./db/{encoded}.json'):
                        with open(f'./db/{encoded}.json', 'r') as file:
                            json_data = json.load(file)
                            for i, entry in enumerate(json_data):

                                # first item is duplicate system prompt
                                if i == 0:
                                    continue

                                history.append(entry)

                    # add latest user prompt
                    history.append({
                        "role": "user",
                        "content": body
                    })

                    # compute response
                    response: str = ""
                    try:
                        cr: ChatResponse = chat(model=model, messages=history)
                        response = cr.message.content
                    except Exception as e:
                        response = str(e)

                    # parse out relevant model
                    response_body: str = f''
                    if default_model:
                        response_body = f'{subject_by_words[0]} not a permitted model, using default model {model}.\n\n'
                    response_body += response

                    # create email object
                    response_message = MIMEMultipart()
                    response_message["From"] = login["email"]
                    response_message["To"] = sender
                    if subject.startswith("Re:"):
                        response_message["Subject"] = subject
                    else:
                        response_message["Subject"] = f"Re:{subject}"
                    response_message.attach(MIMEText(response_body, "plain"))

                    # send email
                    try:
                        with smtplib.SMTP_SSL(login["smtp_addr"], login["smtp_port"]) as server:
                            server.login(login["email"].split('@')[0], login["password"])
                            server.send_message(response_message)
                        print("Email sent successfully!")
                    except Exception as e:
                        print(f"Error: {e}")

                    history.append({
                        "role": "assistant",
                        "content": response,
                    })

                    with open(f'./db/{encoded}.json', 'w', encoding="utf-8") as file:
                        json.dump(history, file, indent=4)

        mail.logout()
    except Exception as e:
        print(f"Error: {e}")

    # stop from raping my poor vps
    # stalwart is light, but it needs all the help it can get
    sleep(30)
