# Audit dan use case HEBAT lokal

Jalankan `scripts/test_hebat.py`, `scripts/test_reader.py`, `scripts/test_history.py`, `scripts/test_regressions.py`, `scripts/test_attachment.py`, serta pengujian autentikasi di runtime `hebat_mcp/test_auth.py`. Gunakan fixture palsu untuk kondisi password salah, jaringan gagal, dan Keychain ditolak; jangan memaksa kegagalan akun kampus. Struktur skill dapat diuji dengan validator skill-creator, tetapi fixture dan validator tidak membuktikan kompatibilitas akun nyata.

## Kasus perilaku dan bukti yang diperlukan

| Skenario | Hasil yang harus terlihat |
|---|---|
| “Prioritas tugasku sekarang” dari cwd/chat lain | Satu `priority`; semester terdeteksi ditampilkan; indeks hanya pada cakupan itu; detail kandidat terdekat; tidak scan penuh lalu filter |
| “Ringkas ulang hasil tadi” | `show`, zero HTTP, timestamp sumber tetap |
| Jawaban rutin tentang materi/tugas | Tidak menambahkan footer “Dicek …” atau jam pemeriksaan; deadline tetap jelas. Waktu pemeriksaan dijelaskan jika diminta atau kesegaran data memengaruhi kesimpulan |
| “Cari tugas AVD teo yang tenggatnya prioritas” dengan satu tugas | Langsung jawab instruksi lengkap, syarat, format/nama berkas, deadline, presentasi, pengunggah, status, dan tautan sesuai sumber; tidak menunggu permintaan detail. Ringkasan priority terpotong dilengkapi lewat satu native assignment_detail tanpa fresh/helper bila hasil detail sudah lengkap |
| “Dalami tugas ini” dari chat lain | Menjelaskan inti pekerjaan, tabel ketentuan sumber, arti praktis, hal yang perlu diverifikasi, saran yang ditandai bukan kewajiban, status dan tautan; tidak mengarang aturan, memulai pengerjaan, atau menambahkan footer waktu. Format disesuaikan dengan jenis tugas |
| “Detail tugas pertama” / “baca lengkap” | URL hasil dipakai pada native assignment_detail dahulu; instructions_truncated=false berarti selesai tanpa helper/shell |
| Instruksi native terpotong | Satu helper detail URL sama --full, memakai cache hasil native tanpa fresh tambahan |
| Native tidak tersedia / diketahui build lama | Helper langsung sebagai pengganti, tanpa mencoba semua jalur atau check berulang |
| “AVD praktikum I1” | Nama lengkap indeks dipakai; tidak tercampur teori atau I2 |
| “Aku baru mengumpulkan, cek lagi” | `--fresh`, perubahan status dapat terlihat tanpa memaksa login baru |
| “Cek seluruh semester” | `scan --all-semesters`; hasil tersimpan satu kali; tampilan dipaginasi |
| Sesi valid | Satu verifikasi per operasi baca, bukan sebelum setiap halaman |
| Sesi berakhir di tengah pembacaan | Satu pemulihan terbatas; retry dihentikan bila tetap ditolak |
| Password ditolak / form login berubah | Blokir percobaan lanjutan sampai pengaturan diperbarui; tidak mengulang setiap tool call |
| Keychain terkunci/ditolak | Error spesifik; tidak fallback ke cookie/password file |
| Konteks shell berbeda | Error dengan kode OS, gunakan eksekusi host yang diizinkan satu kali; jangan menyimpulkan perlu akun ulang |
| Submitted tetapi Not graded | Dikecualikan dari belum terkumpul |
| Draft | Tetap perlu ditindaklanjuti |
| Pengumpulan oleh wakil kelompok | Catatan bahwa status satu akun bukan bukti status kelompok |
| Indeks tanpa tahun | Hanya perkiraan untuk kandidat; tenggat akhir wajib tahun lengkap dari detail |
| Perpanjangan | Tenggat perpanjangan terverifikasi dipakai sebagai efektif, tanggal asli dipertahankan |
| Halaman/kelas gagal dibaca | `errors`/`warnings` tetap terlihat; tidak dianggap kelas tanpa tugas |
| Query tulis kosong, origin lain, redirect tulis | Ditolak sebelum GET; jangan kirim probe tulis ke kampus |
| Cache akademik | Mode file 0600/folder 0700, terikat akun, umur jelas, tidak menyimpan credential/token/HTML mentah |
| Ekspor skill/runtime | Hanya source yang ditentukan; tidak `.session`, `.cache`, cookie, credential, atau venv |

Untuk uji hidup, ukur waktu, HTTP GET/POST, jumlah halaman/detail, ukuran output, dan timestamp. Gunakan satu scan bila audit lengkap diperlukan; jangan mengulang akses kampus hanya untuk mengganti format. Bandingkan cakupan yang sama untuk klaim percepatan. Prioritas dan audit semua semester mempunyai cakupan berbeda, sehingga perbandingannya harus diberi penjelasan.

Jangan menjanjikan seluruh aktivitas tercakup atau waktu tertentu sebelum diukur. Bedakan waktu helper dari waktu agent membaca panduan, mengambil keputusan, dan menyusun jawaban. Uji dari cwd lain memvalidasi penemuan runtime, bukan bukti bahwa model lain sudah mengikuti skill pada chat baru.

## Regresi riwayat

Uji riwayat berulang tanpa HTTP; pergantian rentang hari tanpa fetch ulang; submit baru hanya fetch detail terkait; revisi dengan status sama lewat changed-url; pembaruan recent lima menit dan historical satu jam; tarik ke Draft lalu resubmit; perbedaan status indeks/detail; refresh gagal lalu retry; bootstrap cache detail lama; paginasi tanpa HTTP; dan dua query bersamaan tanpa duplikasi cold read. Simulasikan perubahan pada fixture, bukan dengan mengunggah/mengubah tugas kampus. Uji hidup cukup memeriksa hitungan fetch/cache dan pembaruan khusus satu tugas yang sudah dikenal.

## Regresi keamanan, konsistensi, dan lampiran

- Simulasikan setup yang terputus di setiap penulisan Keychain. Sesi B tidak boleh diterima dengan identitas/cache A; lakukan hanya pada MemoryStore fixture.
- Uji redirect login menuju logout, route tulis, origin lain, serta redirect lampiran; pastikan target terlarang tidak pernah diminta. Uji jaringan gagal tanpa mengulang password.
- Uji beberapa halaman kembali ke login, termasuk pekerja bersamaan; seluruh operasi berbagi satu anggaran pemulihan.
- Uji prioritas, lalu detail/history yang lebih segar, lalu prioritas lagi. Hasil tidak boleh bertentangan dengan bukti baru dan tidak perlu HTTP tambahan bila sumber masih valid. `show` tetap historis.
- Uji JSON terpotong atau valid dengan tipe salah, field hilang, timestamp boolean/NaN/Infinity/masa depan, schema lama, serta ledger salah bentuk. Cache miss harus pulih tanpa crash; kegagalan sumber tetap terlihat.
- Uji status indeks/detail unknown, waktu Last modified tepat sekarang dan sedikit di masa depan, batas tujuh hari dan tahun. Tidak ada item yang hilang diam-diam.
- Uji filter ID/nama lengkap dengan kelas lain yang tidak cocok; indeks mereka tidak dibaca. Label pendek ambigu boleh diresolusi dan semua nama lengkap yang ditemukan disimpan.
- Uji perpanjangan yang menggeser kandidat awal melewati kandidat batch berikutnya. Hasil diurutkan dari tanggal detail, dengan batas cakupan tetap terlihat.
- Uji lampiran instruksi, submission, feedback, dan unknown; `forcedownload=1`; PDF gagal unduh; tujuan sudah ada. Tidak menimpa berkas atau meninggalkan hasil setengah jadi.
- Uji penguncian dua proses dan proses yang mati saat menyimpan: berkas lama atau baru tetap utuh; tidak ada JSON setengah jadi.

Periksa `checked_at` sebagai sumber relevan tertua, `index_checked_at` terpisah, dan waktu pemeriksaan detail. Validasi paket dengan allowlist sumber dan manifest hash; tidak memasukkan cache, sesi, credential, cookie, venv, atau HTML akun.

## Regresi materi dan uji tanpa riwayat

Jalankan juga `scripts/test_material.py`. Uji satu nama kelas tanpa ID/URL, alias KBSI/ISIT, label kelas terpotong, kelas ambigu, urutan bagian numerik dan aktivitas, dua PDF di antara PPT, serta Resource dengan redirect atau embed. Penolakan origin lain, logout, query tulis, halaman tanpa berkas, beberapa berkas, serta sesi habis tidak boleh memicu browser atau tebakan sumber. Kasus asli `attachment URL_RESOURCE --output PATH` harus lolos.

Untuk uji perilaku independen yang diminta pengguna, agent menerima hanya lokasi skill dan permintaan membaca PDF terbaru KBSI. Jangan beri ID, URL, path berkas lama, atau jawaban yang diharapkan. Verifikasi bahwa berkas valid dibaca sebelum jawaban, tautan absolut diberikan langsung, tugas dibedakan dari instruksi pengumpulan, dan pertanyaan slide lanjutan tidak mengunduh ulang. Laporkan waktu proses dan waktu agent secara terpisah; uji CLI dari cwd berbeda saja bukan bukti uji agent tanpa riwayat.

## Pemakaian ulang berkas materi

Uji memperluas limit 1 menjadi 3: file pertama dipakai ulang, hanya dua kandidat baru diunduh. Pengulangan limit 3 tidak boleh meminta Resource/pluginfile lagi; halaman kelas boleh tetap diperiksa. Periksa path identik, files_reused/files_downloaded, checked_at sumber tetap, dan hash/ukuran/izin lokal. Uji file hilang, korup dengan ukuran sama, path di luar akun, symlink, metadata rusak/akun berbeda, serta dua pemanggilan serentak. fresh harus membaca sumber kembali dan tidak menimpa berkas lama; tujuan output eksplisit tetap mengikuti larangan menimpa. Berkas yang diganti di URL sama tidak terdeteksi dari pemeriksaan lokal saja: gunakan fresh saat pembaruan sumber diminta. Cache akademik tetap schema 4, sesi tetap format 2, tidak ada daemon atau dependensi baru.

## Regresi helper lintas aplikasi pada Mac

Jalankan scripts/test_runtime_binding.py dan tools/test_release.py pada runtime. Uji bind-runtime privat/atomik/idempoten/konflik; pointer valid/rusak/hilang; path dengan spasi dan symlink Python venv yang tidak boleh di-resolve keluar venv; tidak ada CLI Codex; cwd berbeda; fallback Codex lama termasuk disabled; runtime worker dan peluncur login tidak berubah mengikuti pointer yang diganti kemudian. Uji builder dengan/tanpa --claude-skill-root, kesamaan file bersama, tidak menyalin metadata Codex, penolakan symlink keluar tujuan, dan pemeriksaan arsip sumber.

Pengujian akun nyata memakai sesi baru Codex dan Claude Code: prioritas, detail tugas, history, dan PDF KBSI beserta analisis dan tautan lokal. Verifikasi delapan tool, versi/build yang sama, penggunaan ulang PDF lintas aplikasi, dan pertanyaan slide lanjutan tanpa unduhan. Jejak panggilan harus membuktikan tindakan, bukan hanya jawaban agent. Catat waktu tool terpisah dari seluruh giliran; izin normal tetap berlaku. Hash reader/server/auth/Keychain/login harus tetap sama untuk perubahan integrasi ini.
