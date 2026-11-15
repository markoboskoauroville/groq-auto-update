When: Marko asks for pictures of yoga poses (asanas), or any new picture "in the style of Svemir's Wyoga images" (the flat green silhouette woman,
orange sun disc, pale sage background), for the Asana Guide (Mantra) app or anything else. Marko, 15.11.2026: "poses for yoga create with Queen in this machine."
Where: ONLY the chromium-vm's Gemini image worker (Drive batch), never Gemini in the Mac's Chrome. Nothing generated comes to the Mac except the final images.
Steps:
1. The style refs: Svemir's own images in ~/Developer/ASANA_GUIDE_DATA/refs (standing.png, tree.png, warrior-ii.png, down-dog.png). Attach all four to EVERY item.
2. One item per pose: `{name: "<pose-id>", prompt: <STYLE> + "Pose: <the pose described from the side or front, anatomy>"}`. STYLE = "Square 1:1 flat illustration in exactly the same style
   as the four reference pictures (image 1 is the main one): the same woman, a solid dark forest-green silhouette with a subtle painted texture, a large soft orange
   sun disc behind her upper body, a very pale sage-green background, a thin dark ground line under her feet, calm empty space, same framing and scale. Exactly one person,
   no text, no watermark. Anatomy correct: two arms, two legs, five fingers, both feet." The full working batch is ~/Developer/ASANA_GUIDE_DATA/gen/batch-asana-guide.json.
3. `POST /api/vm-gemini/batch {name, folder:"Gemini/asana-guide", refs:[the four paths], items:[...]}` starts it (Chrome and the worker are started on the VM; accounts
   auroville.community then gmail.com). `GET /api/vm-gemini/status?folder=Gemini/asana-guide` shows the pictures made (about one a minute) and the worker's log.
4. Look at every picture before using it: correct pose, ONE person, the same woman (silhouette, sun, colours), hands and feet right. A wrong one: move it to `<folder>/_wrong/`
   on Drive (the worker makes it again) after sharpening that item's prompt; at most 2 retries per pose, then say so.
5. `POST /api/vm-gemini/fetch {folder, names, to}` copies only the accepted finals to the app's folder. Left-right pairs of a pose are made by mirroring one picture, not generated twice.
Traps: if the worker logs "no Chrome profile signed in", the VM's Chrome has no Gemini window for that account: the route opens them, then restarts the worker.
Mirrored sides: flip horizontally. Free route only (no paid imgtoimg). Images are Svemir's style: credit "Images: Wyoga by Svemir", publishing outside needs his OK.
