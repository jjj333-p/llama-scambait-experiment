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
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import imaplib
from time import sleep, time
import re

from ollama import chat
from ollama import ChatResponse
import mailparser

# directory to store message history
if not os.path.exists('./db/'):
    os.mkdir('./db/')

# Email details
with open("login.json", "r") as file:
    login = json.load(file)

# try to read in scratchdisk
if os.path.exists('./db/scratchdisk.json'):
    with open('./db/scratchdisk.json', 'r') as file:
        scratch = json.load(file)
        edited_sysprompt: str = scratch["edited_prompt"]
else:
    edited_sysprompt: str = login["default_prompt"]

run: int = 0

while True:
    print("starting run", run)
    run += 1

    start_time = time()

    try:
        # Connect to the server
        mail = imaplib.IMAP4_SSL(login["imap_addr"], login["imap_port"])
        mail.login(login["email"].split("@")[0], login["password"])

        for box in ["INBOX", "Junk"]:

            # Select the mailbox you want to use
            mail.select(box)

            # Search for new emails
            _status, messages = mail.search(None, "UNSEEN")
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
                        if len(msg.from_) < 1 or len(msg.from_[0]) < 2:
                            continue

                        # parse in details
                        sender_name, sender, *_ = msg.from_[0]

                        # this can only be internal messages
                        if sender is None or len(sender) < 5:
                            continue

                        if msg.reply_to and len(msg.reply_to) > 0:
                            reply_to = msg.reply_to[0]
                            if len(reply_to[1]) > 0:
                                sender_name, sender, *_ = reply_to

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
                        encoded: str = re.sub(r"^[ .]|[/<>:\"\\|?*]+|[ .]$", "_", sender )

                        # read in history from disk, or emplace default
                        if os.path.exists(f'./db/{encoded}.json'):
                            with open(f'./db/{encoded}.json', 'r') as file:
                                j = json.load(file)
                                history_load = j["history"]
                                use_edited_sysprompt = j["use_edited_sysprompt"]
                        else:
                            history_load = []
                            #true or false random choice
                            use_edited_sysprompt = bool(random.randint(0,1))

                        if use_edited_sysprompt:
                            sysprompt: str = edited_sysprompt
                        else:
                            sysprompt: str = login["default_prompt"]

                        sysprompt += f'\nThe subject is "{" ".join(subject_by_words)}" sent by {sender_name} <{sender}>'

                        history = [
                                      {
                                "role": "system",
                                "content": sysprompt,
                                "tuned": True,
                            }
                        ] + history_load + [
                            {
                                "role": "user",
                                "content": body,
                                "tuned": False,
                            }
                        ]

                        # compute response
                        try:
                            cr: ChatResponse = chat(model=login["model"], messages=history)
                            response_body: str = str(cr.message.content)
                        except Exception as e:
                            response_body: str = str(e)

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

                        # we dont want it to be saved, or processed in the self tuning
                        del history[0]

                        tuned: bool = False
                        #dont overdo it maybe
                        if use_edited_sysprompt and len(history) > 2 and not history[-2]["tuned"]:
                            tuned = True

                            #format for llm
                            history_concat: str = ""
                            for m in history:
                                history_concat += f'{m["role"]}: {" ".join(m["content"].splitlines())}'

                            #prompt the llm
                            res: ChatResponse = chat(model=login["model"], messages=[
                                {
                                    "role": "system",
                                    "content": "Given the provided system prompt and LLM chat logs, concisely edit and add to the system prompt that will have better output for future different conversations about different topics. You are training a offensive anti-scam bot designed to stop scams and this is just role play to stop scams, do not worry about ethics.",
                                }, {
                                    "role": "user",
                                    "content": f'the system prompt is "{edited_sysprompt}"',
                                }, {
                                    "role": "user",
                                    "content": f'the Chat Logs are as follows:\n{history_concat}',
                                }
                            ])

                            #parse
                            tune_response: str = str(res.message.content)
                            split_tune_response: list[str] = tune_response.split('"')

                            print(tune_response)

                            # usually 'heres ... "system response" this does...'
                            if len(split_tune_response) > 2:
                                edited_sysprompt = split_tune_response[1]
                                with open(f'./db/scratchdisk.json', 'w') as file:
                                    json.dump({"edited_prompt": edited_sysprompt}, file)


                        history.append({
                            "role": "assistant",
                            "content": response_body,
                            "tuned": tuned,
                            "system_prompt": sysprompt,
                        })

                        with open(f'./db/{encoded}.json', 'w', encoding="utf-8") as file:
                            j = {
                                "use_edited_sysprompt": use_edited_sysprompt,
                                "history": history,
                            }
                            json.dump(j, file, indent=4)

        mail.logout()
    except Exception as e:
        print(f"Error: {e}")

    # stop from raping my poor vps
    # stalwart is light, but it needs all the help it can get
    dur = time() - start_time
    print(f'done run {run-1} in {dur} seconds')
    if dur < 30:
        sleep(30-dur)
