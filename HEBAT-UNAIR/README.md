# HEBAT MCP & Agent Skill

Hubungkan agent AI dengan HEBAT UNAIR untuk memahami tugas, menentukan prioritas tenggat, menelusuri riwayat pengumpulan, dan membaca materi kuliah lewat percakapan.

Proyek ini memadukan **MCP lokal** untuk mengakses informasi kampus dan **Agent Skill** untuk memandu cara agent membaca serta menjelaskan hasilnya. Instruksi tugas dan dokumen sumber diperiksa sebelum diringkas; kredensial dan sesi login tetap tersimpan di **macOS Keychain**.

**macOS · Python 3.11+ · MCP stdio · Codex dan integrasi Claude Code · Akses HEBAT baca saja**

[Pemasangan](docs/INSTALLATION.md) · [Cara kerja](docs/ARCHITECTURE.md) · [Pengujian](docs/TESTING.md) · [Asal proyek](docs/UPSTREAM.md)

## Mulai dari pertanyaanmu

Setelah MCP dan skill dipasang, kamu bisa meminta:

- **Prioritas:** “Cari tugas yang deadline-nya paling dekat sekarang.”
- **Penjelasan tugas:** “Dalami tugas ini: ketentuannya apa, apa yang perlu disiapkan, dan bagaimana pengumpulannya?”
- **Riwayat:** “Tugas apa saja yang sudah kukumpulkan seminggu terakhir?”
- **Materi:** “Baca PDF terbaru KBSI, jelaskan ada tugas atau instruksi pengumpulan nggak, dan langsung kasih PDF-nya.”
- **Tindak lanjut:** “Slide 5 maksudnya apa?” atau “Buka materi sebelum yang tadi.”

Jawaban tugas diarahkan untuk memuat ketentuan dosen, deadline, format berkas, aturan pengunggah, status akun, dan tautan sumber. Saat diminta mendalami, agent menjelaskan arti praktis persyaratan serta membedakan **kewajiban dosen, interpretasi, dan saran**. Ketentuan yang tidak tercantum tidak diisi dengan tebakan.

Untuk materi, berkas asli diambil dan dibaca sebelum diringkas. Tautan lokal langsung disertakan agar pengguna bisa membuka dokumen yang sama. Pertanyaan lanjutan dapat memakai berkas atau hasil pembacaan yang sudah tersedia.

## Kemampuan yang tersedia

| Kebutuhan | Hasil | Tool MCP |
|---|---|---|
| Menentukan prioritas | Urutan tenggat, status, serta tugas terlambat yang dipisahkan | `hebat_priority` |
| Memahami satu tugas | Instruksi, deadline, status, aturan pengumpulan, dan tautan lampiran | `hebat_assignment_detail` |
| Melihat riwayat | Tugas berstatus terkumpul berdasarkan waktu perubahan terakhir | `hebat_submission_history` |
| Membaca materi kelas | Penemuan Resource, unduhan berkas, dan path lokal terverifikasi | `hebat_material` |
| Menemukan kelas/aktivitas | Daftar kelas dan tautan aktivitas | `hebat_courses`, `hebat_assignments` |
| Memeriksa akses | Ringkasan dashboard serta status sesi/build | `hebat_dashboard`, `hebat_status` |

Nama atau singkatan seperti **KBSI, ISIT, AVD, PAP, dan PPL** dicocokkan dengan kelas pada akun pengguna. Kelas teori, praktikum, dan paralel dibedakan. Jika hasil masih ambigu, agent perlu memperjelas kelasnya.

## Bagaimana komponennya bekerja

```text
Pertanyaan → agent mengikuti skill → tool MCP → reader → HEBAT
                                             ↕
                                   Keychain, cache, dan file lokal

Hasil terstruktur / berkas → agent membaca dan menjelaskan → jawaban + tautan
```

- **Skill** mengarahkan pemilihan operasi dan cara menjelaskan hasil. Native MCP diutamakan bila tool yang sesuai tersedia.
- **Server MCP** menyediakan delapan tool yang bisa dipanggil aplikasi agent.
- **Reader** membaca halaman HEBAT, mengolah kelas/tugas/tanggal/status, serta mengambil dan memeriksa berkas.
- **Helper** menyediakan operasi CLI dan jalur pengganti ketika diperlukan. Setelah runtime diikat, helper tidak memerlukan CLI Codex.
- **Cache** mengurangi pembacaan berulang. Berkas lokal diperiksa ukuran, hash, izin, dan kepemilikan akunnya sebelum dipakai ulang. Permintaan pembaruan sumber menggunakan `fresh`.

Reader menyediakan data dan berkas; penjelasan isi PDF/presentasi dilakukan oleh agent dengan pembaca dokumen yang tersedia. Satu runtime dapat digunakan oleh Codex dan Claude Code, dengan proses MCP masing-masing.

## Pemasangan di Mac

Yang diperlukan:

- Python **3.11+** pada macOS.
- Akun HEBAT UNAIR milik pengguna sendiri.
- Codex atau Claude Code dengan dukungan MCP lokal dan akses model yang sesuai. Pemasangan proyek ini tidak memberikan akses model berbayar.

Dari direktori `HEBAT-UNAIR`, siapkan lingkungan Python:

```bash
python3 -m venv runtime/.venv
runtime/.venv/bin/python -m pip install -r runtime/requirements.txt
```

Lanjutkan [panduan pemasangan](docs/INSTALLATION.md) untuk:

1. Memasang skill pada aplikasi yang dipakai.
2. Mengikat lokasi Python dan server pada penunjuk runtime lokal.
3. Mendaftarkan MCP `hebat`.
4. Mengatur akun sendiri melalui Terminal dan memverifikasi koneksi.

Pemasangan saat ini dilakukan melalui langkah eksplisit. Lokasi instalasi ditentukan pengguna; contoh konfigurasi tidak memerlukan path Mac pengembang.

## Status pengujian dan batas dukungan

| Bagian | Status |
|---|---|
| Reader / server | **2.3.2 / 0.4.2** |
| Native Codex | Pembacaan akun nyata diuji pada lingkungan pengembangan |
| Claude Code | Skill dikenali dan MCP terhubung; operasi protocol MCP serta file bersama diuji. **Percakapan penuh dengan model Claude belum terverifikasi** |
| Pemasangan pada Mac lain | Belum diverifikasi |
| Windows, Claude web, Claude Desktop | Belum termasuk pemasangan yang diuji pada proyek ini |

Hal yang perlu dipahami saat membaca hasil:

- Prioritas mencakup **aktivitas Assignment yang ditemukan**. Kuis, forum, aktivitas tersembunyi, dan tugas di luar HEBAT dapat tidak tercakup. Hasil yang parsial tetap diberi keterangan.
- Status akun sendiri belum membuktikan status kelompok jika pengumpulan cukup dilakukan oleh perwakilan. “Belum dinilai” juga berbeda dari “belum dikumpulkan”.
- Riwayat memakai waktu perubahan terakhir, bukan log seluruh versi pengumpulan.
- Materi “terakhir” mengikuti urutan bagian/pertemuan dan aktivitas yang tersedia, bukan tanggal unggah yang belum diketahui.
- File lokal yang utuh belum membuktikan isi di URL sumber tidak berubah. Gunakan pembaruan sumber saat diperlukan.
- Struktur HTML atau SSO HEBAT dapat berubah. Tes fixture tidak membuktikan seluruh kelas dan akun selalu kompatibel.

## Privasi dan batas akses

Seluruh operasi kampus bersifat **baca saja**. POST hanya digunakan untuk autentikasi. Tidak tersedia operasi unggah tugas, kirim pesan, ubah profil, atau hapus data kampus.

NIM/password diisi sendiri oleh pengguna di Terminal dan disimpan di Keychain bersama sesi. Jangan mengirim kredensial melalui chat. Hasil pembacaan HEBAT diteruskan ke aplikasi agent yang digunakan untuk menyusun jawaban; penyimpanan kredensial lokal tidak berarti percakapan AI berjalan seluruhnya di Mac.

Sumber proyek dipisahkan dari data pengguna. Jangan commit atau membagikan cookie, `.session`, `.cache`, penunjuk runtime lokal, unduhan materi, keluaran akun, atau konfigurasi pribadi aplikasi agent.

## Struktur proyek

```text
HEBAT-UNAIR/
├── runtime/
│   ├── hebat_mcp/            # reader, server MCP, auth, login, dan tes
│   ├── requirements.txt
│   └── tools/                # builder distribusi dan tesnya
├── skills/
│   └── hebat-unair/          # SKILL.md, helper, referensi, dan tes
├── docs/                     # pemasangan, arsitektur, pengujian, dan asal proyek
├── LICENSE
└── NOTICE.md
```

Reader pada runtime adalah sumber utama. Builder menyinkronkan salinannya pada skill dan memeriksa kesamaan hash. Paket distribusi dibuat dari daftar berkas sumber eksplisit dan dilengkapi manifest.

Lihat [pengujian dan distribusi](docs/TESTING.md) untuk menjalankan tes atau membuat paket.

## Lisensi dan sumber awal

Proyek ini dikembangkan dari **[Arroyan23/MCP-Kampus](https://github.com/Arroyan23/MCP-Kampus)**, yang ditemukan melalui **[Glama](https://glama.ai/mcp/servers/Arroyan23/MCP-Kampus)**. Sumber awal menyediakan MCP HEBAT baca saja; pengembangan lanjutan menambahkan reader terstruktur, Keychain, cache, riwayat, pembacaan materi, helper, dan skill.

MIT. README proyek awal menyatakan lisensi MIT. Atribusi dan snapshot asal dicatat di [NOTICE.md](NOTICE.md) dan [asal proyek](docs/UPSTREAM.md).
