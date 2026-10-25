# Pemasangan lokal pada Mac

## 1. Siapkan runtime

Dari direktori HEBAT-UNAIR, buat `runtime/.venv` dan pasang `runtime/requirements.txt` sesuai README. Gunakan path absolut Python venv tersebut dan `runtime/hebat_mcp/server.py` untuk langkah berikut. Pertahankan path executable di dalam venv; jangan menggantinya dengan target symlink Python sistem.

## 2. Pasang skill

- Codex: pasang folder `skills/hebat-unair` pada lokasi skill yang didukung instalasi Codex-mu. Instalasi pengembangan memakai `~/.codex/skills/hebat-unair`; dokumentasi Codex saat ini juga mencantumkan `~/.agents/skills`. Pilih satu yang dikenali, jangan memasang dua salinan bernama sama tanpa kebutuhan.
- Claude Code: pasang file skill bersama di `~/.claude/skills/hebat-unair`, tanpa metadata Codex `agents/openai.yaml`. Builder dapat menyiapkannya:

```bash
python3 runtime/tools/release.py --claude-skill-root "$HOME/.claude/skills/hebat-unair" --output-dir dist
```

Builder membaca sumber skill dari repo ini. Penyalinan hanya mencakup berkas sumber yang ditentukan. Jika sudah memiliki instalasi skill, periksa perubahan dan buat cadangan sebelum menggantinya.

## 3. Ikat lokasi runtime

Jalankan helper dari repo atau dari instalasi skill. Ganti placeholder berikut dengan path absolut yang benar:

```text
python3 skills/hebat-unair/scripts/hebat.py bind-runtime --python /absolute/path/HEBAT-UNAIR/runtime/.venv/bin/python --server /absolute/path/HEBAT-UNAIR/runtime/hebat_mcp/server.py
```

File penunjuk privat dibuat di `~/.config/hebat-unair/runtime.json`. Ini bukan tempat menyimpan NIM/password. Binding sama idempoten; jika sudah terikat ke instalasi lain, helper melaporkan konflik. Jangan menghapus atau mengganti binding lama sebelum memastikan runtime yang ingin digunakan.

## 4. Daftarkan MCP

Gunakan nama server `hebat` agar sesuai dengan panduan skill. Jika sudah terdaftar, periksa dan pertahankan instalasi yang benar; jangan menambahkan ulang secara membabi buta.

Codex:

```text
codex mcp add hebat -- /absolute/path/HEBAT-UNAIR/runtime/.venv/bin/python /absolute/path/HEBAT-UNAIR/runtime/hebat_mcp/server.py
```

Claude Code:

```text
claude mcp add --scope user --transport stdio hebat -- /absolute/path/HEBAT-UNAIR/runtime/.venv/bin/python /absolute/path/HEBAT-UNAIR/runtime/hebat_mcp/server.py
```

Kedua aplikasi boleh menunjuk runtime yang sama; masing-masing menjalankan proses stdio sendiri. Akses model Claude Code mengikuti layanan akunmu dan tidak diberikan oleh pemasangan skill/MCP.

## 5. Atur akun sendiri

```bash
python3 skills/hebat-unair/scripts/hebat.py setup-keychain
```

Pengguna mengisi akun langsung di Terminal. Jangan mengirim password atau cookie ke agent/chat. Jika akun sudah tersedia di Keychain, tidak perlu mengaturnya ulang hanya karena berganti aplikasi. Gunakan izin normal Mac/aplikasi; jangan melewati penolakan Keychain.

## 6. Verifikasi

```bash
python3 skills/hebat-unair/scripts/hebat.py check
```

Periksa akun terautentikasi serta versi/build. Setelah tool tersedia di sesi agent, minta prioritas tugas atau pembacaan materi. Claude Code memakai `/hebat-unair`; Codex dapat memakai skill hebat-unair sesuai cara pemanggilan instalasinya. Proses MCP lama perlu dimulai ulang hanya jika kode runtime berubah.

Referensi: [Codex MCP](https://developers.openai.com/codex/mcp), [Codex skills](https://developers.openai.com/codex/skills), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Claude Code skills](https://code.claude.com/docs/en/skills).
