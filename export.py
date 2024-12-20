"""
This code is provided on an as-is warranty-free basis by Joseph Winkie <jjj333.p.1325@gmail.com>

This code file is specifically to export the stored conversation history in a readable markdown format

This code is licensed under the A-GPL 3.0 license found both in the "LICENSE" file of the root of this repository
as well as https://www.gnu.org/licenses/agpl-3.0.en.html. Read it to know your rights.

A complete copy of this codebase as well as runtime instructions can be found at
https://github.com/jjj333-p/llama-scambait/
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

if __name__ != "__main__":
    raise ImportError("This script should only be run directly and not imported.")

#parse in length arg
parser = argparse.ArgumentParser(description="Process some CLI arguments.")
parser.add_argument(
    "--length", "-l",
    type=int,
    required=False,
    default=0,
    help="Specify the length of conversation to format, provided as an integer. Number is multiplied by 2 (i.e. one message one AI response)."
)
args = parser.parse_args()
length_to_parse: int = args.length*2

# for debug
print(f"Generating markdown file for all conversations of length {args.length} or more.")

default_sysprompt: str = ""
edited_sysprompt: str = ""

with open("login.json") as file:
    json_login = json.load(file)

    if not json_login.get("default_prompt"):
        raise RuntimeError("Default prompt not in login.json.")

    default_sysprompt: str = json_login["default_prompt"]

# somewhere to store
conversations: dict[str, dict] = {}

#read in all stored json files
for file in Path("db").iterdir():

    # need to parse
    if not file.suffix == ".json" or not file.is_file():
        continue

    # apparently python is happy to just write incomplete json
    try:
        json_file = json.load(open(file))
    except Exception as e:
        print(f"Could not read {file} as JSON with error: {e}.")
        continue

    # special case
    if file.name == "scratchdisk.json":
        #interested field from this file
        if json_file.get("edited_prompt"):
            edited_sysprompt = json_file["edited_prompt"]
        continue
    else:
        conversations[file.stem] = json_file

# header
current_date: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
md_output: str = (f"# Current AI Scambait conversations\n\n"
                  f"Conversations >{length_to_parse} messages.\n"
                  f"Export date: {current_date}\n")

if len(default_sysprompt) > 0:

    md_output += "## Default System Prompt\n"

    for line in default_sysprompt.splitlines(keepends=True):
        md_output += f"> {line}"

    md_output += "\n"


if len(edited_sysprompt) > 0:

    md_output += "## Edited System Prompt\n"

    for line in edited_sysprompt.splitlines(keepends=True):
        md_output += f"> {line}"

    md_output += "\n"

# generated formatted output
for email, conversation in conversations.items():

    # if sufficient conversation history
    if not conversation.get("history"):
        continue
    if len(conversation["history"]) < length_to_parse:
        continue

    # title email
    md_output += f"## Conversation {email}\n"

    match conversation.get("use_edited_sysprompt"):
        case True:
            md_output += "Conversation **is** using edited system prompt.\n"
        case False:
            md_output += "Conversation **is not** using edited system prompt.\n"
        case False:
            md_output += "It is unknown if this conversation is using a default or edited system prompt.\n"

    md_output += f"Conversation length **{len(conversation['history'])}**.\n"

    # format each message
    for msg in conversation["history"]:
        match msg.get("role"):
            case "user":
                md_output += "### User/Scammer\n"
            case "assistant":
                md_output += "### AI response\n"
            case _:
                md_output += "### Unknown source\n"

        if msg.get("system_prompt") and conversation.get("use_edited_sysprompt") is True:
            md_output += "Current system prompt:\n"
            for line in msg['system_prompt'].splitlines(keepends=True):
                md_output += f"> {line}"
            md_output += "\n\n"

        if msg.get("content"):
            md_output += f"Body Content:\n"
            for line in msg['content'].splitlines(keepends=True):
                # escape out code that makes it go insane latex mode (see https://envs.sh/7wT.png )
                md_output += f"> {r"\$".join(line.split("$"))}"
        else:
            md_output += "Missing body content."

        md_output += "\n\n"

try:
    with open("out.md", "w") as file:
        file.write(md_output)
except Exception as e:
    print(f"Could not write to Out.md file. Would you like to print to stdout? \n{e}.")
    res:str = str(input(f"Print to stdout? [Y/n]")).lower()
    if res == "y" or res == "yes":
        print(md_output)

print("Done.")