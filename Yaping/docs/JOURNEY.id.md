# Cerita di balik Yaping

🇬🇧 [English](JOURNEY.md) · 🇮🇩 Bahasa Indonesia

Yaping berkembang dari folder kosong menjadi aplikasi dikte yang dipakai sehari-hari hanya dalam **satu hari: 10 Oktober 2026**. Semuanya berawal dari satu kalimat: *"buatkan aplikasi seperti Wispr Flow untukku."*

Yaping dibuat oleh **Naufal Zaki**, yang mengarahkan dan menguji setiap langkah, sebagian besar lewat suara memakai Yaping sendiri, tanpa mengetik kode secara manual. [Claude Code](https://claude.com/claude-code) berperan sebagai rekan pemrograman. Setiap keputusan desain di bawah ini didasarkan pada tes nyata di MacBook sungguhan (Apple M3, 16 GB). Semua angka di halaman ini berasal dari log waktu Yaping, yang hanya mencatat durasi dan jumlah kata, tidak pernah isi ucapan.

---

## 1. Versi pertama: lokal dan gratis

Targetnya "gratis dan jalan lokal di Mac-ku". Versi pertama menggabungkan:

- **whisper.cpp** dengan model `large-v3-turbo` untuk suara-ke-teks, dijalankan sebagai server latar belakang supaya selalu siap
- **Qwen 3.5 9B** lewat Ollama untuk parafrase dan perbaikan grammar

| Tes (rekaman sintetis Bahasa Indonesia, 13 detik) | Hasil |
| --- | --- |
| Transkripsi Whisper lokal | **~3,0 detik**, semua kata tepat |
| Parafrase Qwen lokal | **~2,0 detik**. Kalimat *"jam tiga, eh bukan, maksudnya jam empat"* dengan tepat diubah menjadi "16.00" |

**Eksperimen yang ditolak.** Memperkecil jendela audio Whisper memang mempercepat transkripsi (3,0 detik menjadi 1,8 detik), tapi pada ukuran tertentu hasilnya kacau: huruf asing dan kata-kata karangan. Kecepatan tidak sebanding dengan teks yang salah, jadi trik itu dibuang.

## 2. Parafrase: sengaja dimatikan

Parafrase dipindahkan ke API gratis Groq supaya kualitasnya lebih baik. Lalu satu dikte sungguhan sempat tertahan **46 detik** karena Groq tidak merespons. Perbaikannya: batas tunggu 6 detik dengan model cadangan otomatis. Dengan itu, kasus terburuk turun ke sekitar 11 detik, dan parafrase biasanya selesai dalam kurang dari 1 detik.

Lalu muncul keputusan produk: **transkrip mentah ternyata lebih enak dibaca.** Parafrase membuat bahasa santai jadi terlalu formal ("gimana" menjadi "bagaimana") dan kadang menghilangkan nuansa. Parafrase AI akhirnya dimatikan secara bawaan.

## 3. Gemini vs Groq: uji langsung

Naufal mendikte dengan masing-masing mesin:

| | Groq (Whisper turbo) | **Gemini 3.5 Transcribe** |
| --- | --- | --- |
| Tanda baca | Tidak ada sama sekali: 64 kata dalam satu kalimat panjang | Titik dan koma rapi di setiap kalimat |
| Nama merek | "Grog" di satu tempat, "Groq" di tempat lain | "Gemini 3.5 transcribe" dan "Groq" ditulis benar |
| Kecepatan | 2,4 detik (audio 33 detik) | 3,3 detik (audio 46 detik) |

**Gemini menang telak.** Mode *smart*-nya membuang "eh/emm" dan mengikuti koreksi diri tanpa mengubah kata-katamu. Itu persis jalan tengah antara teks mentah dan parafrase.

## 4. Uji kualitas 5 menit

Apakah Yaping sanggup menangani bicara panjang, misalnya rapat? Naufal bicara tanpa henti selama lima menit.

Berhasil, dan tidak ada kata yang hilang. Tapi waktu tunggunya **143 detik**, dan datanya menunjukkan alasannya: Gemini melambat secara tidak seimbang pada audio panjang.

| Durasi audio | Waktu proses | Detik proses per detik suara |
| --- | --- | --- |
| 24 detik | 3,1 detik | 0,12 |
| 59 detik | 8,2 detik | 0,14 |
| 85 detik | 14,8 detik | 0,17 |
| **306 detik (5 menit)** | **143,0 detik** | **0,47**, hampir 4× lebih buruk |

Perkiraan awalnya sekitar 45 detik. Tes membuktikan perkiraan itu salah, dan memang itulah gunanya tes.

## 5. Pemotongan otomatis: dari 143 detik ke 2,3 detik

Solusinya: rekaman panjang dipotong di jeda alami menjadi bagian-bagian sekitar 1 menit, lalu masing-masing ditranskripsi **selagi pengguna masih bicara**. Saat berhenti, tinggal potongan terakhir yang perlu diproses. Ukuran potongannya ditentukan dari tabel di atas: audio sekitar 1 menit adalah titik paling efisien.

Lalu tes 5 menit yang sama diulang:

| | Sebelum | **Sesudah pemotongan** |
| --- | --- | --- |
| Durasi | 5 menit 6 detik | 4 menit 58 detik |
| Jumlah potongan | 1 | 7 |
| **Menunggu setelah selesai** | **143 detik** | **2,3 detik** (sekitar 60× lebih cepat) |
| Potongan gagal | – | 0 |

Sekarang teks juga muncul bertahap, per potongan, selagi kamu terus bicara.

## 6. Menabrak batas tier gratis, lalu mendesain solusinya

Di tengah satu sesi, satu potongan kembali kosong. Log menunjukkan penyebabnya: **tier gratis Gemini hanya mengizinkan 25 request per hari**, dan tes hari itu sudah menghabiskannya. Satu menit ucapan hilang.

Jawabannya adalah rantai cadangan yang sadar kuota:

```
Gemini (utama) ──▶ Groq (cadangan) ──▶ Whisper lokal (offline)
```

Sekarang Yaping membaca jam tunggu persis dari pesan error Google (*"retry in 10h59m"*), melewati Gemini sampai waktunya tiba, dan menampilkan sisa kuota di menu bar.

**Terbukti di kondisi nyata.** Tak lama setelah dipasang, satu dikte sungguhan sepanjang 85 detik mengalami *dua* kegagalan berturut-turut: kuota Gemini habis, **lalu Wi-Fi putus saat Groq sedang mentranskripsi**. Yaping beralih ke Whisper lokal dan menyerahkan semua 129 kata tanpa kehilangan satu kalimat pun.

## 7. Perbaikan kecil yang ditemukan dari pemakaian

Memakai aplikasinya sehari-hari memunculkan masalah yang tidak akan terpikir di rancangan awal:

- whisper.cpp menaruh tiap frasa di baris baru → sekarang segmen digabung menjadi paragraf utuh
- Dikte berturut-turut menempel ("bagaimana?Tapi") → spasi otomatis berdasarkan karakter sebelum kursor
- Whisper menulis tarikan napas setelah jeda sebagai "Hai" → dibuang di tengah teks, tapi dipertahankan sebagai sapaan di awal
- Istilah teknis salah dengar ("CPP" → "pipi", "API" → "EPK") → kosakata pribadi, yang benar-benar dipakai oleh Gemini
- Di macOS 27, Accessibility pindah ke *Device Control and Data Access* → dokumentasi dan tombol izin diperbarui

## Hasil akhir

| | |
| --- | --- |
| Dikte pendek | ~1,5–3 detik dari selesai bicara sampai teks muncul |
| Dikte 5 menit | ~2–10 detik dari selesai bicara sampai teks muncul |
| Bahasa | Indonesia, Inggris, dan campuran |
| Biaya | Gratis |
| Beban saat diam | ~190 MB RAM, ~0,5% CPU |

Pelajaran yang muncul di setiap langkah: **ukur, jangan menebak.** Setiap kali perkiraan bertemu tes sungguhan, tesnya yang menang, dan aplikasinya jadi lebih baik karenanya.
