#!/usr/bin/env bash
# PostToolUse: segnala quando la versione in pyproject.toml non corrisponde a
# quella registrata in uv.lock.
#
# uv.lock pinna anche la versione del pacchetto stesso, quindi diventa stantio a
# ogni bump. Nel rilascio della v0.2.4 il bump era arrivato da una PR che non
# aveva rifatto `uv lock`: il lock e' rimasto a 0.2.3 e nessuno degli step di
# docs/release.md se ne e' accorto. Il documento protegge chi lo legge, questo
# hook chi non lo legge.
#
# Esce 2 con il messaggio su stderr: l'edit e' gia' avvenuto, quindi non si
# blocca nulla, si chiede di rimettere in pari il lock.
set -u

payload=$(cat)
f=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$f" in */pyproject.toml | pyproject.toml) ;; *) exit 0 ;; esac

cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
root=$(git -C "${cwd:-$PWD}" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$root/pyproject.toml" ] && [ -f "$root/uv.lock" ] || exit 0

# Il nome non e' cablato: cosi' l'hook non marcisce se il pacchetto viene
# rinominato, e resta riusabile in un altro progetto uv.
name=$(sed -n 's/^name = "\(.*\)"$/\1/p' "$root/pyproject.toml" | head -1)
proj=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$root/pyproject.toml" | head -1)
[ -n "$name" ] && [ -n "$proj" ] || exit 0

lock=$(grep -A1 "^name = \"$name\"\$" "$root/uv.lock" | sed -n 's/^version = "\(.*\)"$/\1/p' | head -1)
[ -n "$lock" ] || exit 0

if [ "$proj" != "$lock" ]; then
  {
    printf 'uv.lock e fuori sincrono: pyproject.toml dice %s, uv.lock dice %s.\n' "$proj" "$lock"
    printf "Esegui 'uv lock' e verifica che il lock sia cambiato (docs/release.md, step 2).\n"
  } >&2
  exit 2
fi
exit 0
