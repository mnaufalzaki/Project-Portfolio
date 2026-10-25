# Koneksi, cache, dan pemulihan HEBAT

## Runtime bersama dan pemasangan per aplikasi

Penunjuk lokal `~/.config/hebat-unair/runtime.json` memuat hanya `version: 1`, `python` (path absolut executable venv), dan `server` (path absolut server.py). Kredensial tetap di Keychain. Helper memakai penunjuk ini tanpa mencari CLI Codex/Claude. Jika penunjuk tidak ada, konfigurasi `codex mcp get hebat --json` lama tetap didukung; penunjuk rusak atau berkas hilang tidak memicu fallback.

- Python: `<runtime-root>/.venv/bin/python`.
- Server: `<runtime-root>/hebat_mcp/server.py`.
- Ikat runtime sekali: `python3 '<skill-dir>/scripts/hebat.py' bind-runtime --python '<runtime-root>/.venv/bin/python' --server '<runtime-root>/hebat_mcp/server.py'`. Ganti placeholder dengan lokasi absolut instalasi yang dipilih; tidak ada path akun pengembang yang wajib diikuti.
- Pengulangan binding yang sama tidak menulis ulang. Runtime berbeda menghasilkan `runtime_binding_conflict`; jangan mengganti diam-diam. Folder/file penunjuk wajib privat 0700/0600. Tidak menyimpan penunjuk ke Git atau paket distribusi.
- Codex: pertahankan MCP `hebat` yang sudah terdaftar dengan Python dan server ini, serta instalasi skill yang sudah berfungsi. Metadata `agents/openai.yaml` hanya untuk Codex.
- Claude Code: daftarkan lewat `claude mcp add --scope user --transport stdio hebat -- '<runtime-root>/.venv/bin/python' '<runtime-root>/hebat_mcp/server.py'`. Skill personal berada di `~/.claude/skills/hebat-unair/`; panggil `/hebat-unair` atau permintaan alami. User scope membuat MCP tersedia lintas proyek, tanpa konfigurasi proyek baru.
- Kedua aplikasi menjalankan proses stdio sendiri, memakai satu sumber runtime, Keychain service, dan cache per akun. Jangan menggandakan runtime atau meminta pengaturan akun ulang hanya karena berganti aplikasi.
- Helper meneruskan runtime yang dipilih ke worker dan peluncur Terminal. Perubahan penunjuk sesudah peluncuran tidak mengalihkan proses login yang sudah dipilih.

- `auth.py` dan `keychain_store.py`: autentikasi Keychain yang sudah diverifikasi.
- `reader.py`: parser, pemakaian sesi per operasi, cache akademik privat, dan pemilihan prioritas. Runtime adalah sumber utama. `release.py` menyalin reader ke scripts skill dan memeriksa kesamaan sebelum membuat arsip sumber. `build_id` pada keluaran object mengidentifikasi kode yang dimuat; proses lama tidak otomatis memuat perubahan berkas.
- `login.py`: pengaturan akun oleh pengguna sendiri di Terminal.

MCP versi ini menyediakan status, courses, assignments, dashboard ringkas, priority, submission_history, assignment_detail, dan material. Semua tool diberi anotasi baca saja. Proses chat lama dapat masih memakai versi sebelumnya; helper memulai kode baru, sehingga tidak perlu meminta akun atau mengubah konfigurasi hanya untuk melanjutkan tugas.

## Operasi praktis

- `priority`: semester terbaru yang terdeteksi, detail kandidat terdekat, sebagian overdue, dan tanggal tidak jelas. Default lima prioritas; `--limit` dapat diubah 1–50. `--course` mendukung nama/kode kelas dan singkatan AVD/PPL/PAP/KBSI/ISIT; teori dan praktikum dibedakan.
- Detail tugas: native `hebat_assignment_detail(url=URL)` terlebih dahulu. Bila `instructions_truncated=false`, hasil sudah cukup tanpa shell/helper. Helper `detail 'URL' --full` untuk hasil native terpotong, tool tidak tersedia, atau build lama yang sudah diketahui. Sesudah native, gunakan URL sama dan cache yang tersedia; jangan menambah fresh tanpa alasan kesegaran baru.
- `material --course kbsi --file-type pdf --limit 2`: temukan dan unduh dua PDF terakhir kelas, tanpa browser. URL Resource langsung dapat dipakai sebagai argumen material; nama kelas dan URL saling eksklusif. Hasil materials berisi local_path untuk dibaca dan langsung ditautkan. Urutan berdasarkan bagian/pertemuan, bukan tanggal unggah. Unduhan otomatis privat di `.cache/hebat-materials/<hash-identitas>/`.
- `attachment 'URL' --output 'PATH'`: unduh satu lampiran melalui sesi terikat akun; URL Resource diselesaikan ke berkas; URL dan setiap redirect harus lolos validator HTTPS HEBAT Resource/`pluginfile.php` yang sesuai konteks. Query yang diizinkan hanya kosong atau `forcedownload=0/1`. Parent tujuan wajib privat `0700`; helper membuat parent yang belum ada, tetapi menolak parent bersama yang sudah ada. Tujuan baru ditulis atomik `0600`; berkas lama tidak ditimpa. Respons HTML ditolak sebagai lampiran, bukan disimpan sebagai PDF.
- `history --days 7`: ledger riwayat Last modified seluruh kelas; indeks berubah hanya menyegarkan detail terkait. `--recheck-index` melewati TTL indeks; `--changed-url URL` memeriksa revisi satu tugas; `--fresh` memverifikasi semua kandidat.
- `show --kind history`: riwayat tersimpan tanpa HTTP.
- `show`: hasil prioritas tersimpan tanpa HTTP. `show --kind scan --offset 20 --limit 20`: lanjutkan audit tersimpan tanpa scan ulang.
- `scan --semester LABEL` atau `scan --all-semesters`: audit lebih luas yang diperlukan pengguna. Hasil lengkap tersimpan lokal, sementara keluaran agent dipaginasi.
- `--fresh`: membaca ulang sumber akademik, bukan memaksa login baru. Gunakan setelah pengguna baru mengumpulkan tugas.
- `check`: handshake proses MCP baru; exit nonzero bila akun tidak aktif. `refresh`: satu login paksa hanya untuk audit autentikasi yang diminta.

`checked_at` mempertahankan waktu sumber tertua yang relevan pada hasil campuran cache; `assembled_at` adalah waktu perangkuman. Detail mempertahankan waktu pemeriksaannya sendiri. `from_cache`/umur cache tidak boleh disebut sebagai pemeriksaan jaringan baru.

## Keychain dan data lokal

Service Keychain: `id.ac.unair.hebat.codex`. Item internal: credentials, session, control. NIM/password berada dalam payload terenkripsi item, bukan label atau account item. API Security.framework/CoreFoundation dipakai langsung dari memori, tanpa rahasia di argv/environment/output. Tidak mengubah izin semua aplikasi dan tidak menonaktifkan proteksi macOS.

Cache berada di `<runtime-root>/.cache/hebat-reader/<hash-identitas-akun>/schema-4/`. Hash membedakan akun; bukan pengganti enkripsi untuk data akademik. Folder akun 0700, file 0600, ditulis secara atomik. Cache hanya data akademik yang sudah diparse, tanpa HTML mentah, cookie, password, atau token login. Jangan memasukkan cache ke arsip skill/runtime. Identitas akun berubah berarti cache akun lama tidak digunakan. `last-priority.json` dan `last-scan.json` menyimpan hasil lengkap terbaru, sehingga pengubahan format tidak membutuhkan jaringan.

TTL: daftar kelas 600 detik; indeks, detail, dan hasil prioritas maksimal 120 detik. `show` boleh membuka hasil yang lebih lama; jelaskan usia data bila memengaruhi kesimpulan, tanpa footer waktu pemeriksaan otomatis pada jawaban rutin. Header cache schema 4 memuat identitas pemilik; format lama tidak dipercaya dan dibiarkan tetap privat di disk. Subfolder schema memisahkan writer versi lama yang masih berjalan dari cache baru; ini tetap cache yang sama, bukan lapisan tambahan. Operasi berikut membangun kembali cakupan yang diminta saja. Sesi Keychain envelope v2 juga terikat pemilik; sesi lama tanpa pemilik diperbarui memakai kredensial yang sudah tersedia, tanpa meminta akun ulang. Tidak ada scan semua semester otomatis saat migrasi.

Satu operasi memverifikasi sesi sekali, lalu memakai sesi per pekerja (maksimal tiga). Jika halaman kembali ke login, seluruh operasi berbagi anggaran satu pemulihan; maksimal satu login otomatis termasuk pembaruan sesi awal. Redirect autentikasi hanya boleh menuju route login atau tujuan baca yang diizinkan, bukan logout/perubahan akun. Password ditolak/form berubah menghentikan tebakan lanjutan melalui kontrol auth. Kegagalan jaringan tidak memicu tebakan password. Tidak ada fallback plaintext; `.session/auth.lock` hanya lock tanpa rahasia.

## Error dan pengaturan

| Kondisi | Tindakan |
|---|---|
| `network_unavailable` | Tampilkan sumber/cakupan parsial; ulangi hanya halaman yang diperlukan |
| `keychain_operation_failed` dan OSStatus -50 pada shell terbatas | Jika host yang sesuai tersedia dan belum ditolak, gunakan mekanisme izin shell host sekali; bukan alasan meminta NIM/password lagi |
| `keychain_locked_or_permission_required` | Pengguna membuka/mengizinkan Keychain sendiri |
| `credentials_update_required` / `credentials_rejected` | Perbarui melalui setup-keychain; hentikan percobaan berulang |
| `login_form_or_sso_changed` | Tinjau integrasi tanpa melewati CAPTCHA/SSO |
| `no_matching_course` | Periksa `courses`, bedakan semester dan kelas paralel; jangan menganggap tidak ada tugas |
| `no_saved_result` | Jalankan operasi sumber sekali; bukan scan berulang untuk format |

`setup-keychain` membuka **Setup-Keychain-HEBAT.command** melalui tool shell, bukan Computer Use/AppleScript pengendali Terminal. Receipt hanya metadata proses; proses mulai belum membuktikan jendela terlihat atau login selesai. Verifikasi akun setelah pengguna menyelesaikan input. Cookie teks lama dihapus hanya setelah sesi Keychain ditulis, dibaca ulang, dan berhasil dipakai klien baru.

Sumber runtime asal: https://github.com/Arroyan23/MCP-Kampus. Penggunaan tetap lokal; Secure MCP Tunnel tidak dipasang sebagai koneksi aktif.

## Cache riwayat tambahan

`history-ledger.json` menyimpan fingerprint indeks dan ringkasan status/Last modified per tugas, terikat akun yang sama. Data akademik, bukan credential. `last-history.json` menyimpan hasil query terbaru untuk paginasi. Lock privat `.history.lock` mencegah dua query bersamaan mengulang seluruh pembacaan. Indeks memakai TTL 120 detik; detail dengan Last modified dalam tujuh hari terakhir memakai TTL 300 detik, detail lebih lama 3600 detik. Perubahan fingerprint dan changed-url mengabaikan TTL detail terkait; fresh mengabaikan semua cache data. Ledger dapat mengadopsi cache detail yang sudah ada jika masih valid, sehingga pemasangan fitur tidak otomatis mengulang semua detail.

Pemeriksaan TTL terjadi saat ada permintaan, tanpa daemon/jadwal baru. Revisi yang tidak mengubah indeks baru terlihat lewat changed-url, fresh, atau pemeriksaan detail berkala. Jangan menyatakan ada notifikasi perubahan langsung dari HEBAT.

## Audit performa dan distribusi

Tambahkan `--audit-metrics` pada operasi helper untuk melihat hitungan dan durasi operasi tersebut. Hitungan HTTP mencakup percobaan autentikasi, redirect, dan retry; `pages_read_this_run` hanya menghitung halaman reader yang berhasil. Cache hit metadata bukan selalu akses jaringan yang dihindari. Jangan menyamakan keduanya. Keluaran normal tetap ringkas.

Ukur jaringan, verifikasi sesi, cache, parser, unduh, ekstraksi PDF, render, dan alur agent secara terpisah. Durasi fixture lokal bukan durasi HEBAT nyata. Sisa waktu di luar tool tetap belum terklasifikasi sampai jejak aksinya diperiksa.

Arsip dibuat dari allowlist sumber, bukan seluruh folder runtime/skill. Daftar kelas native tetap berbentuk daftar; metadata build ditambahkan pada keluaran object dan status. Tidak ada daemon, tunnel, atau layanan publik.

Builder distribusi tersedia di `tools/release.py` pada runtime. Pemeriksaan sumber tanpa perubahan: `python3 tools/release.py --check`. Untuk membuat dan memeriksa ulang paket, gunakan `python3 tools/release.py --output-dir 'PATH'` lalu `python3 tools/release.py --check --output-dir 'PATH'`. `--runtime-root` dan `--skill-root` memilih lokasi sumber secara eksplisit bila berbeda dari instalasi standar. Builder hanya membaca allowlist sumber dan tidak mengakses Keychain atau kampus.

## Pembaruan skill kedua aplikasi

Gunakan builder yang ada dengan `--claude-skill-root ~/.claude/skills/hebat-unair` untuk menyinkronkan file bersama dari sumber skill Codex; `--check` dengan opsi yang sama hanya memverifikasi salinan. Tanpa opsi itu, perilaku builder lama tetap. File agents/openai.yaml tidak disalin ke Claude. Format penjelasan tugas, pembacaan PDF, tautan langsung, dan penghilangan footer waktu tetap sama di kedua aplikasi. Gunakan kemampuan pembaca dokumen yang tersedia; tidak mewajibkan skill PDF/presentasi khusus Codex atau memasang dependensi baru secara otomatis. Jangan mengklaim isi sudah dibaca jika pembacaan gagal.

Jika aplikasi menolak akses shell, file lokal, atau Keychain, ikuti izin normal aplikasi tersebut; jangan memakai aplikasi lain untuk melewati penolakan. Login akun Claude Code berbeda dari login HEBAT dan dilakukan melalui alur resmi Claude Code jika diperlukan.

Dokumentasi client: https://code.claude.com/docs/en/mcp dan https://code.claude.com/docs/en/skills .
