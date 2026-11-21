# forcekit — Send to Force

## Intent
Damian copies exported kits to the Force by hand. The Force has Wi-Fi, SSH (root, key login already
works from his computer) and an SSD. He wants a **Send to Force** button that puts the current kit on
the Force, all sent kits in one folder there, and the Force's address configurable in the app.

## Goals / non-goals / anti-goals
- Goals: a button that exports the current program and copies it to the Force; all sent programs under
  one folder on the Force (`<force dir>/Drums/<Name>/`, `<force dir>/Synths/<Name>/`, each holding
  `<Name>.xpm` + `<Name>_[ProgramData]/`); settings in the page for IP, user and folder; a connection test.
- Non-goals: sending the whole library at once, deleting from the Force, password logins.
- Anti-goals: a half-copied kit on the Force after a dropped connection; replacing a kit on the Force
  without asking; storing passwords; touching anything on the Force outside the forcekit folder.

## Approaches
1. **tar streamed over ssh (chosen):** the Force has `tar` and `sftp-server` but no rsync. One ssh call
   extracts into a temp folder and swaps it in, so replacement is all-or-nothing.
2. scp/sftp of the folder: no atomic swap without extra round trips.
3. Mounting the SSD over the network: nothing on the Force serves SMB/NFS.

## Design
- Config gains `force_host` (default `192.168.0.27`), `force_user` (`root`), `force_dir`
  (`/media/96B6-573E/forcekit`), saved into `~/.config/forcekit/config.json` (other keys kept).
  `ssh_command` (default `["ssh"]`) is internal, for tests.
- `forcekit/send.py`: `test_connection`, `send_program(cfg, local_program_folder, overwrite)`.
  ssh runs with `BatchMode=yes` and a short connect timeout; any failure becomes a readable error
  (unreachable / login failed → mention `ssh-copy-id`). The tar stream is built in Python (GNU format,
  owner root). Remote: extract into `<type dir>/.<Name>.forcekit-tmp`, then replace `<type dir>/<Name>`;
  the temp folder is always removed. Names are shell-quoted.
- Server: `GET/PUT /api/settings`, `POST /api/settings/test`, `POST /api/send {draft, normalize,
  overwrite}` → exports locally (overwriting the local export) then sends; 409 if the program exists on
  the Force and `overwrite` is false; 502 with the message if the Force can't be reached.
- Page: **Send to Force** next to Export (inline "Replace on Force?" confirm on 409); **⚙ Settings** in the
  top bar: IP, user, folder, Test connection, Save.

## Verification
Unit tests with a stand-in `ssh` that runs the remote command locally: first send, refusal without
overwrite, replace, failed copy leaves the old kit, names with spaces/quotes, settings round trip.
Then one real send to the Force and a listing of the forcekit folder.
