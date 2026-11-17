# Requests, word for word

16.11.2026, Marko: "Please expand the pause to macro recorder and Queen. All our tools need to be paused at the same time and need to have this kind of API calls to be stopped."
Done: POST /api/pause, POST /api/resume, GET /api/pause/status ({"paused","since","queued"}), chat "pause" / "resume" / "pause status", `queen pause|resume`, skill queen_skills/pause-all.md, state ~/.groq/pause.json shared by the Swift app (v7) and the Python backend (qwen_app/pause_state.py); registered in ~/.config/claude-control/tools.json.

11.11.2026, Marko: "please research the command from the terminal qwen Write in the skill open GitHub repository. Call it
groq_ai_studio, and write everything you know about this app there. Also copy the source code and make it public. Of course you
don't copy any API keys or any secrets there. Only the pure code. We are developing this app now."
Done: repo created from ~/.groq (qwen_app, groq_pool, groq_cli, launchers), TAKEOVER.md, LESSONS.md, skill.

12.11.2026, Marko (Mac session, while the Santoshi posters were being built):
> I hope that's clear, but I'm just enforcing it. Anything we are doing now is becoming a skill for Queen. Next time I ask her a similar question, she can do this without you claude code

> write this in the manifest of this repository in the takeaways, lessons, and also skills: Every time I ask you to do something, true queen, you need to teach her, you need to write a skill so next time if I ask directly, she's able to do it without you Enforce the rule, please.

> since you are online, you establish this connection between Queen and you. She can read remote sessions, she can talk to you, and you can talk to her. She can ask you questions, and you can ask her questions and give her solutions. But if we are online, she's not contacting the API at Tropic. No way. Or API Go Google. If there is a local connection with you, Cloud Code, that's the priority. If it's missing, she's asking, "I cannot reach the local Cloud Code. Do you want to use API credits?" Then we use API credits. We are trying to avoid using API credits

12.11.2026, Marko (sent to the Academy session by mistake, forwarded word for word):
> now let's see if she can change the queen image. Let's ask her to find an image when the band is from behind, and we see the audience, and use this picture as a background picture. Make the poster A4 aspect ratio, portrait. There is already a poster made by AI on the site. Look at this poster and copy its layout, but using the real picture

> She does not understand what behind means. I can see she took a front photo. Please you choose for her you just offer her the photo is the same photo looking like the one which is made with poster, but it's not ai. I use ai to enhance the photo

> after that, you tell her that this photo is not good quality, that she needs to create a photo in Google Gemini for free. I tell her that this photo is vertical and the photo is horizontal. The poster is vertical, and we are missing the parts of the photo. Let her take this poster inside Gemini and then make it, what is missing, to be extended

> after generating the new, better image with AI, which fills the whole frame, she needs to create English and Croatian posters, two versions

> continue building. After that, make another version of the poster with three horizontal stripes dividing the poster in three parts. The upper part is similar to now: pink lights regenerate pink lights inside Gemini. Then, the down part, make a stripe with pictures of band members

> to remind me of the skill: if it's not well written, you need to go through it. When you exhaust one account from the Chrome browser, you just switch to another profile and then continue there. All the photos are saved locally in the Pictures folder, by today's date and project name, and then they are used in the poster building

> please, in the same folder, save all the poster versions as PNGs, and the format which I can edit as Affinity Vector Format or Affinity Bitmap Format, but I need layers

> and please assess how Queen is doing and update her skills so she can do this better next time

> also test her skills of describing images by taking all the images from Santoshi's website, describing them, and then in the same folder, write an Excel sheet with the description of each image

> each image needs to have its own sheet, i.e., tab, inside the sheet. On the tab, there is an image name, and inside is a description

> also, if images are not generating, if there is a timeout, or if they are not generating after a few minutes, you need to go to the next profile

> please ask Queen to press the button to allow remote debugging. So if I'm not here, that button should be pressed, asking our macro recorder to do it in natural motion with real mouse and keyboard

## 12.11.2026, 17:40

> /Users/markobosko/Pictures/Panorama Stitching/IMG_20251217_124553537_PANORAMA.tiff Please make this photo small size, good for web, and add it to the photo gallery inside my website Kuklica Eco Oasis.

> please teach Queen how to do this Now you need to supervise her before each move. She's going to ask approval from you, so she doesn't mess up my website.

> in queue with new task. Open the new chat with the title of the task, please

> yes, self-checking. You need to teach her to self-check everything she does. Make a new interface for her, for Queen, in tabs, so each task is in a different tab. We have: - Settings task - Auto-update task - Chat task If you can find any more groupings, make it like this, so it's organizing better. The real estate of the application is used. Also, make an Easter egg, Groq Studio. There is an icon which is lightning. When I click on it, I go to full screen, and when I click again, I come back

> please teach her how to screenshot and confirm that things are live. She can recognize, she can compare the image of what she did and find it on the page, and confirm the image is there

**Status of the 12.11.2026 requests:** all done and pushed (skills folder and teach-Queen rule; local Claude link and API consent;
Gemini posters EN/HR full-bleed and three stripes; account fallback; Pictures folder and .af + .png; Excel catalogue; assessment;
Allow press by Macro Recorder; supervised web-photo with the panorama live; one chat per task; self-check; tabs; lightning
full-screen). Open: the full-screen click not tested by a real click.

13.11.2026, Marko: "please open the virtual machine in Mantra Remote and rename this repository and application to Mantra Remote
Viewing Also, open the Queen and everything. I ask you now to do it through the Queen. Put in the standing rule for this computer:
everything we are doing through the Queen. Everything we are doing here, we are using the Queen to teach her how to do the things.
Now, this renaming, she needs to understand. You stop doing anything physically in this computer: moving things, renaming things.
Mantra, Macro, and Queen are doing everything. You are just giving the tasks. You are writing the skills, and you are assessing and
reviewing what I did and making corrections. You are the master teacher of this tool. I am telling you what to do, and you use those
guys to test them, assess them, fix them. You always need to do corrections until they come to the level of your Opus model."

13.11.2026, Marko: "please also update the user interface. She needs to always summarize where we are. Give a kind of one-sentence
description of where we are now and what we are doing. There is a model name at the top, next to the model name, like a current
situation news channel with one or two sentences maximum, three. Then you can move this plus/minus zooming in the line with tabs
next to the settings. We have a news channel thing reporting what's going on in the chat in a summarized view at the top. Let's
make it max 4 sentences"

13.11.2026, Marko (on names): "The name can be an approximation. It can be just a symbol of the name. It needs to find the best
matching, even an abbreviation. It needs to find what is the only match. It needs to offer me the top 5 matches ... what she thinks
makes the most sense needs to be at the top."

13.11.2026, Marko: "Make mi wan prompt hir. You could prompt Claude like this: "Claude, please generate code that sets up an
automated workflow where Qwen's output and its corrections by the Opus model are recorded in a GitHub repository. The code
should log each Qwen output, capture Opus's correction, and prepare a dataset for periodic fine-tuning. Include steps for data
storage, versioning, and triggering the training process.""

13.11.2026, Marko: "You are a senior AI engineer. Help me build a Hugging Face fine-tuning workflow. Goal: I use Qwen for tasks.
Claude reviews Qwen's answers and provides corrections. I want to turn those corrections into a dataset. I want to periodically
fine-tune Qwen using SFT and QLoRA. I want to save the resulting adapter to my private Hugging Face Hub repository. Please give
me: 1. A JSONL dataset format for instruction, Qwen answer, corrected answer, and feedback. 2. A Python script using Hugging Face
TRL SFTTrainer and PEFT QLoRA. 3. A script to upload the dataset and trained adapter to Hugging Face Hub. 4. A simple evaluation
plan to compare the original Qwen and fine-tuned Qwen. 5. Clear instructions for GPU memory, batch size, learning rate, and how
often to retrain. Assume I am a beginner and explain each step simply."

13.11.2026, Marko: "Voice engine cannot speak for some reason. It's not important. What is important for me that you make
another repository. Make a book. AI for beginners. And based on my case now training the queen and everything which I pasted
last, make a book explaining and make drawings, sketches on cream paper with a pencil and let queen do all the work. I need that
book to be in my style of design. It needs to have Cloudflare page. It should be called like the name of the book. .pages.dev.
And it needs to be illustrated by three Gemini accounts. I have 21 profiles. 21. Remember, 21 or 22. I'm not sure. On my Chrome
browser. And you can check them out. We generate the whole book for free. Let's do it for free. Let's share the knowledge.
Let's empower the people of the world."

13.11.2026, Marko: "If not already, you confirm. Everything must run the whole operation in the background while I'm using computer.
It means you are using debugging mode in Chrome browser to do the work, so interaction with mouse is not necessary. I can have mouse
and keyboard and speakers to do my work. Is that correct? Donation ball comes to every of my pages, except my own biography and my
dj mantra. For the books, donation yes. it is one more task for Quinn to attach donation balls to all of my books which are on cloud
three and don't forget to mention this cost analysis in the book we just did with RunPod and Groq calls"

13.11.2026, Marko: "don't ask me if I see something. You have screen-capturing possibilities with Macro Recorder and with our Queen, so use that teach the queen to learn to read screens and ask her if there's a subtitle on the screen. She must tell you. If she lies, then you fix her skill."
Status: DONE 13.11.2026 (route /api/screen/look + chat command, skill read-screen.md, installed, restarted, 6 positive / 4 negative trials right after one fix, pushed).

13.11.2026, Marko (word for word): "now, please send another agent to work on this thing in a virtual machine. I want to have the same system as here. There is a Claude Code installed. Queen is not installed. Queen must be in the virtual machine, and everything I'm doing there must be executed with the Queen and Macro Recorder. Macro Recorder needs to be translated to Linux, exactly the same as here. When I'm going there in my virtual machine, I'm asking Claude Code to do two things: it has Macro Recorder, it has Queen, and any lessons or skills are written in the same repository as this computer is doing. It means we are in two locations. We are training Queen and Macro Recorder to be improved, and all this knowledge is coming to the common database for Macro Recorder and the Queen. Please do that and start working on my virtual machine in the background with an agent"
Status: saved first; in progress (two locations: Mac + chromium-vm).

**Status of the 13.11.2026 requests (closing, 14.11.2026):** done: Claude-teaches-only rule; Mantra Remote Viewing renames (Mac v30,
Android v46, repo MANTRA_REMOTE_VIEWING); names by probability; news line + zoom in the tab line; private data repo; training
record + dataset-v1; Hugging Face QLoRA workflow (training/hf, not yet run: needs ~100 examples, a GPU and an HF token);
say-on-phone; one tab; Speak fixed; bandwidth savers (viewer v30, MPA classroom); AI for Beginners (12 chapters, 13 plates,
bowl, live); bowl on Winning Film; Chrome through one permanent connection; the profile box closed by Macro Recorder.
Open: Marko reads the book; HF token; an MPA class to see the snowflake; the keychain question for each new viewer build.

14.11.2026, Marko (word for word): "now it is time to convert our Grok AI Studio into a Swift app. Please do that and upgrade it with new skills for accessibility, and test it like this: ask her to check my last 5 WhatsApp messages, and it needs to understand who sent them and what was not responded to. Without taking screenshots, it needs to use accessibility to get the text"
Then: "WhatsApp, as always, we are using the Firefox browser with something we call remote control"
Status: DONE 14.11.2026: Groq AI Studio (Mantra) v1 (mac_app/, built by GitHub mac-app.yml, installed in /Applications, signed Mantra
Apps), v2 pushed (version badge fix, the updater asks at start); axread; routes /api/ax/read + /api/whatsapp/ax/latest; skills
accessibility.md + whatsapp-accessibility.md; test "check my last 5 WhatsApp messages" answered in her chat from Accessibility, cross-checked,
no screenshot file made. Open: Marko switches Accessibility on for Groq AI Studio (Mantra) (PERMISSIONS) for when the app starts Queen.


Marko, 14.11.2026 (word for word, dictated): "Yes. Delete the flask. Actually, delete it from the system. Yes. Delete it. And, but keep the repository on GitHub. And rename Groq I Studio Mac. Actually, re... Rename the app in Groq slash Queen AI Studio."
Status: DONE 14.11.2026: local folder ~/Developer/GROQ_AI_STUDIO_MAC deleted (repo kept on GitHub); app renamed Groq/Queen AI Studio (Mantra) v3, bundle file "Groq Queen AI Studio (Mantra).app".


Marko, 14.11.2026 (word for word, dictated): "please reduce the output volume on my computer to 10%"
Status: DONE 14.11.2026: volume read back 10; built POST/GET /api/system/volume + local chat command + queen_skills/system-volume.md.


Marko, 14.11.2026 (word for word): "please give Groq queen icon, as we always have icons"
Status: DONE 14.11.2026 (v4): default black six-letter icon GRO/QUE over cursorarrow (six-letter-icon.md), v4.


17.11.2026, Marko (word for word): "Please upgrade my app and don't test it. Just write the code and I'm going to test it myself manually. It's about Queen. I want to have triple chat. And triple chat means there is me in the chat room, there is Claude over API, and there is Groq Queen, our model over API. And in this trio chat box we all can hear each other and comment on each other thoughts. I can ask for example, Queen what do you think about this and she answers. Then I can ask Claude what do you think about this and he answers. And the whole chat history is there and available for everybody. So this is like a pool of three brains where we together discuss and then also we can write the skills, we can also access the GitHub, we can use my computer, so all the skills which Queen already has, she can apply them and also can ask advice. I can for example say, Queen, please ask Claude how to do things and then he explains and she understands. So in this kind of thing, make me triple chat UI, please."
Then: "Before building anything, please write in the takeover of this application what needs to be done. First, write a takeover and then start to build. Because my credits are only 1% and I don't want to lose my prompt, etc. So, takeover needs to be written after every step and right now."
Status: in progress (TAKEOVER.md, TRIPLE CHAT section).

17.11.2026, Marko (word for word): "don't limit me to 8$, just on it, test everything until it works"
Status: in progress (replaces the earlier "don't test it"; TAKEOVER.md, TRIPLE CHAT section, TEST phase).

17.11.2026, Marko (word for word): "Please run another builder, which will use only my API, $100 API, and which is going to open now Queen and test triple mode and report bugs. Actually, it should not report bug. It should have to correct bug."
Status: in progress (API builder opens the real Queen window, tests Triple Chat, fixes bugs; TAKEOVER.md, TRIPLE CHAT — TEST ROUND 2).

17.11.2026, Marko (word for word): "Ask builder to show me the user interface and testing like a real person is using it, typing text, and doing other functions. And for that, it needs to use Macro Recorder and API keys through Groq. A Queen model."
Status: in progress (visible Triple Chat demo by Macro Recorder, Queen as judge; TAKEOVER.md, TRIPLE CHAT — DEMO).

17.11.2026, Marko (word for word): "can queen be used as capi ui can you teach her or add capi tab to queen software so i can have nicer ui also in queen ask worker to add speaker icon at end of each chat response to play audio from chat text using speechify key beatrice voice"
Status: in progress (CAPI tab + speaker icon; TAKEOVER.md, CAPI TAB section).

17.11.2026, Marko (word for word): ask Queen to move ~/Library/LaunchAgents/community.auroville.loginstart.plist to ~/Desktop so iTerm stops opening at login.
Status: hand built (qwen_app/system_files.py, POST /api/system/move, chat "move X to Y", queen_skills/move-file.md); installed, backend restarted; the real move not yet done.

17.11.2026, Marko (word for word): "And next next task is to actually improve Queen itself, this application, and it's ZAPI deal. Zapi part, c a p I part. So we have multiple rooms, so we are not anymore in the rooms. We need to make... Instead of room, make a new conversation and conversations. And when I click on conversations, I see a list of conversations which already exist, but I cannot switch between conversations. I want to be able to work in multiple conversations at the same time. So each conversation should start its own process or its own terminal process. It is running in the background as a parallel process is conversation. And if it's running right now, if it's opened, you need to put on the left edge the green line. And then after every title of every conversation, you need to give me some action buttons. And these action buttons are start and stop. So when I say start, it means it will start new process. In the terminal, it will read all the history of chats, and we can continue chatting. So idea is to continue chatting always through all these. Through many days, we can continue because we are storing the history. And then we will have the third action button, which is close. And closing mean deleting the history and deleting the entry of these chats. Please do that."
Status: in progress (CAPI conversations, v12; TAKEOVER.md, CAPI TAB section).

17.11.2026, Marko (word for word): "Also, add the gear icon at the top of the interface next to the API credits, and this one will just be file picker for API key. And you need to detect API key as we already have everywhere. Even if there is some other text, you extract API key to work with Kepi."
("Kepi" = CAPI.) Status: in progress (v13, gear icon in the CAPI tab, key by shape).

17.11.2026, Marko (word for word): "Add another, quality of life improvement. So I type the prompt. I press send. And when my, my, prompt start to be processed and recognized by API, I want to see con... Confirmation received in the lower right corner next to each prompt. So I know if I need to wait or it's something wrong. So, also, you can add Braille spinner while the API is processing my request so I know it's processing."
Status: in progress (v13, CAPI prompt status sent / received / Braille spinner / failed).
