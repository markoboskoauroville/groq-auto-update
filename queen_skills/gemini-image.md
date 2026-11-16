When: a picture must be made or changed for free: extend a photo to another shape, regenerate a background, enhance.
Call: `POST /api/gemini/image {prompt, image, out}`: Gemini in Marko's Chrome over its DevTools port (remote debugging on,
chrome://inspect/#remote-debugging). Never Firefox, never the download button: the result is a screenshot of the picture.
ORDER since 16.11.2026 (Marko: "You switch account under one account and when this is exhausted then go to switching of the profile. Of course avoiding the accounts which are exhausted."): first the next non-exhausted account in the same tab of the current profile, then, when all accounts of that profile are exhausted, the next Chrome profile as its own window and its accounts; exhausted accounts are skipped everywhere until their reset time. Done by `python3 ~/Developer/MACRO_SKILLS/tools/gemini_account.py switch` (skill gemini-switch-account). The profile list below (12.11.2026) is the profile step.
Accounts (Marko, 12.11.2026): marko.bosko@auroville.community first; when an account is exhausted, refuses, times out or
gives no image within 3 minutes, the next Chrome profile signed in to Google takes over (its window is opened if closed);
the band account santoshi.bend@gmail.com last (it could not edit images on 29.10.2026). At most four accounts per picture.
Save every result in the project's Pictures folder with " (nano banana)" in the name, and reuse it next time (no second
generation for the same picture).
Prompts that work: say what must stay EXACTLY (people, faces, clothes, instruments) and what only may be added (ceiling,
floor, lights); ask for photorealistic, same light and colours.
13.11.2026: new pictures from words alone work (no reference image). The picture is taken as its own file from Chrome's memory
(Page.getResourceContent of the image URL): full size, no Gemini buttons or input bar over it. A screenshot is only the fallback.
Chrome asks "Allow remote debugging?" for every connection; Macro Recorder presses Allow (needs Quartz in Queen's Python).
