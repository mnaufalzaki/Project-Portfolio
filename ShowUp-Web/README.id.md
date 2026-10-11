<div align="center">

<img src="docs/icon.png" width="96" alt="Ikon ShowUp">

# ShowUp

**Aplikasi check-in harian untuk empat kebiasaan tetap. Tahan untuk check-in, lihat harimu menyala, lalu muncul lagi besok.**

![PWA](https://img.shields.io/badge/PWA-bisa%20dipasang-5A0FC8)
![Supabase](https://img.shields.io/badge/Supabase-Auth%20%2B%20Postgres-3FCF8E?logo=supabase&logoColor=white)
![Vanilla JS](https://img.shields.io/badge/Vanilla-HTML%20·%20CSS%20·%20JS-F7DF1E)
![Tanpa streak](https://img.shields.io/badge/streak-tidak%20ada-0B0B0F)

**[Buka aplikasi](https://mnaufalzaki.github.io/Project-Portfolio/ShowUp-Web/)** · 🇬🇧 [English](README.md) · 🇮🇩 Bahasa Indonesia

<img src="docs/preview.png" alt="ShowUp: layar hari ini, proses menahan, perayaan, dan hasil dengan tujuh hari terakhir" width="100%">

</div>

---

## Ringkasan

ShowUp adalah pelacak konsistensi pribadi yang sengaja dibuat kecil. Aplikasi ini bukan pengelola kebiasaan: tidak ada yang perlu ditambah, diganti nama, atau diatur. Empat kebiasaan sudah tetap, masing-masing dengan target harian yang konkret, dan satu-satunya aksi adalah menahan tombol dengan sengaja.

ShowUp berjalan di browser HP maupun laptop, dapat dipasang di Home Screen sebagai Progressive Web App, tetap berfungsi saat offline, dan tersinkron melalui Supabase sehingga kedua perangkat selalu menampilkan hari yang sama.

| Kebiasaan | Target harian |
|---|---|
| **Study** | Minimal 1 jam dengan metode SQ3R |
| **Read** | Minimal 20 halaman |
| **Wake Early** | Gadget off 21.00 · tidur 22.00 · bangun 05.00 |
| **P** | Check-in pribadi yang sengaja tidak diberi keterangan, dikonfirmasi sebelum gadget off |

## Fitur

- **Tahan untuk check-in.** Ring terisi selama 2,5 detik: tombol tertekan, busur terisi dengan ujung yang menyala, titik-titik cahaya terhisap masuk, dan tombol bergetar halus di saat-saat terakhir. Jika dilepas sebelum penuh, semuanya kembali dan tidak ada yang tersimpan.
- **Perayaan yang menampilkan hasil.** Tombol yang ditekan naik ke tengah layar, menyala, lalu hasilnya muncul di bawahnya: jumlah hari ini (misalnya 2/4 → 3/4) dan tujuh hari terakhir, dengan hari ini terisi paling akhir. Setelah itu tombol kembali ke kartunya.
- **Konsistensi, bukan streak.** Setiap kebiasaan memiliki heatmap 18 minggu. Hari yang terlewat hanya berupa satu kotak kosong, bukan penghitung yang kembali ke nol.
- **Tenggat pribadi.** Header menghitung mundur ke pukul 21.00, waktu gadget off. Tampilannya menghangat mulai 19.00 bila masih ada yang belum selesai, menjadi mendesak pada 30 menit terakhir, dan berganti menjadi "Sampai besok" setelahnya. Pergantian hari kalender tetap pukul 00.00 waktu lokal.
- **HP dan laptop, satu sumber data.** PWA yang dapat dipasang dengan cache app shell. Setiap perubahan disimpan ke antrean lokal terlebih dahulu dan disinkronkan ketika koneksi tersedia.
- **Privat sejak awal.** Masuk sekali per perangkat dengan kode enam digit dari email, setelah itu sesi tetap aktif. Row Level Security membatasi setiap baris data hanya untuk pemiliknya.
- **Getaran bila platform mendukung.** `navigator.vibrate` di Android dan teknik haptic switch iOS 18 di Safari, keduanya bersifat best-effort.
- **Aksesibel.** Check-in lewat keyboard (Space atau Enter pada ring yang terfokus), dukungan `prefers-reduced-motion`, target sentuh 44 px, dan ukuran teks minimal 12 px.

## Perbandingan

ShowUp dibangun berdasarkan preferensi satu orang, sehingga perbandingan ini menyoroti kompromi, bukan menentukan pemenang.

| | **ShowUp** | Pelacak berbasis streak (mis. Streaks) | Pelacak bergaya game (mis. Habitica) | Pelacak open-source (mis. Loop Habit Tracker) |
|---|---|---|---|---|
| Pendorong utama | Melihat konsistensi terkumpul | Tidak memutus rantai | Poin, level, quest bersama | Skor kekuatan kebiasaan dan grafik |
| Saat satu hari terlewat | Satu kotak kosong | Streak kembali ke nol | Karakter terkena damage | Skor turun perlahan |
| Pengaturan awal | Tidak ada: empat kebiasaan tetap | Memilih dan mengatur tugas | Membuat habit, daily, to-do | Membuat dan mengatur kebiasaan |
| Gestur menyelesaikan | Menahan 2,5 detik dengan sengaja | Ketuk atau ketuk-tahan | Ketuk | Ketuk |
| Persiapan malam | Hitung mundur tenggat 21.00 bawaan | Pengingat | Pengingat | Pengingat |
| Platform | Browser modern apa pun, bisa dipasang di iOS dan Android | Platform Apple | Web, iOS, Android | Android |
| Data | Project Supabase milik sendiri, antrean offline | Sinkronisasi cloud vendor | Akun vendor | Di perangkat |
| Biaya | Gratis (Supabase free tier, GitHub Pages) | Aplikasi berbayar | Gratis dengan langganan opsional | Gratis |

**Keunggulan ShowUp:** tanpa mekanisme rasa bersalah, tanpa konfigurasi, gestur check-in yang disengaja sehingga tahan salah ketuk, tenggat yang terkait dengan rutinitas tidur nyata, dan kepemilikan data penuh di infrastruktur gratis.

**Kekurangannya, karena disengaja atau belum dikerjakan:** kebiasaan tidak bisa diubah, hanya untuk satu pengguna, getaran di iOS bergantung pada teknik Safari alih-alih API native, dan pengingat belum tersedia.

## Keputusan desain

Pilihan-pilihan ini mencerminkan preferensi pribadi dan diambil dengan sengaja:

- **Tidak ada angka streak di mana pun.** Streak memotivasi lewat rasa takut kehilangan, yang membuat satu hari terlewat terasa seperti alasan untuk menyerah, terutama untuk kebiasaan yang pribadi. Heatmap menghargai konsistensi jangka panjang.
- **Kebiasaan tetap.** Lebih sedikit keputusan berarti lebih sedikit hambatan. Aplikasi ini adalah alat komitmen, bukan perencana.
- **Menahan lama, bukan sekadar mengetuk.** Check-in seharusnya terasa seperti ritual kecil dan tidak pernah terjadi tanpa sengaja.
- **Tenggatnya 21.00, bukan tengah malam.** Gadget dimatikan pukul 21.00 untuk menjaga jam tidur 22.00 dan bangun 05.00, sehingga aplikasi mengingatkan sebelum waktu itu dan mundur setelahnya.
- **"Eat the Frog first."** Pengingat tetap untuk mengerjakan hal paling berat lebih dulu.
- **Tampilan gelap, satu warna per kebiasaan.** Warna harus didapat: kebiasaan yang belum selesai hari ini tampil redup dan baru menyala penuh setelah check-in.

## Teknologi

| Lapisan | Pilihan |
|---|---|
| Front end | Satu `index.html`: HTML, animasi CSS, dan JavaScript murni, tanpa proses build |
| Font | Bricolage Grotesque, Geist, Geist Mono (Google Fonts) |
| Autentikasi dan data | Supabase Auth (kode sekali pakai lewat email) dan Postgres dengan Row Level Security |
| Library klien | `@supabase/supabase-js` 2.45.4 dari jsDelivr |
| Offline | Cache app shell lewat service worker, cache lokal, dan antrean operasi di `localStorage` |
| Hosting | GitHub Pages |

### Model data

Satu baris untuk setiap kebiasaan per hari kalender lokal:

```sql
checkins (
  user_id    uuid  default auth.uid(),
  habit      text  check (habit in ('study', 'read', 'wake', 'p')),
  day        date,
  created_at timestamptz,
  primary key (user_id, habit, day)
)
```

## Menjalankan sendiri

1. Buat project Supabase lalu jalankan [`supabase/schema.sql`](supabase/schema.sql) di SQL Editor.
2. Di **Authentication → Email Templates → Magic Link**, tambahkan kode ke isi email, misalnya `Kode masuk: {{ .Token }}`. Kode (bukan hanya link) memungkinkan login di dalam aplikasi yang terpasang di iOS, karena penyimpanannya terpisah dari Safari.
3. Di **Authentication → URL Configuration**, isi Site URL dengan alamat tempat aplikasi di-hosting.
4. Isi konstanta `SUPA_URL` dan `SUPA_KEY` di `index.html` dengan URL project dan publishable (anon) key. Publishable key aman berada di kode klien; akses dijaga oleh Row Level Security.
5. Hosting folder ini di layanan statis mana pun (di sini memakai GitHub Pages). Setelah login pertama, matikan pendaftaran pengguna baru di Supabase agar orang lain tidak dapat membuat akun.

Untuk melihat tampilan tanpa login, buka `index.html?state=idle` (data demo) atau `index.html?state=done`.

## Struktur proyek

```
ShowUp-Web/
├── index.html             # Seluruh aplikasi: UI, animasi, sinkronisasi data, autentikasi
├── manifest.webmanifest   # Metadata PWA
├── sw.js                  # Service worker (app shell offline)
├── icons/                 # Ikon aplikasi dan Home Screen
├── supabase/schema.sql    # Tabel dan kebijakan Row Level Security
└── docs/                  # Gambar README
```

## Rencana berikutnya

- Pengingat Web Push pukul 19.00 dan 20.30, hanya dikirim bila masih ada kebiasaan yang belum selesai.
- Ringkasan mingguan opsional.

## Pembuat

**Naufal Zaki** · [naufalzaki.tech](https://naufalzaki.tech) · [@mnaufalzaki](https://github.com/mnaufalzaki)
