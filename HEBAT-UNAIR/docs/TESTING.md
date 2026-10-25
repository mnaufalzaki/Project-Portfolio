# Pengujian dan distribusi

Tes berikut memakai fixture; tidak membutuhkan kredensial HEBAT dan tidak mengubah akun kampus. Jalankan dari direktori HEBAT-UNAIR setelah menyiapkan venv:

```bash
runtime/.venv/bin/python -m unittest discover -s runtime/hebat_mcp -p 'test_*.py' -q
runtime/.venv/bin/python -m unittest discover -s skills/hebat-unair/scripts -p 'test_*.py' -q
runtime/.venv/bin/python -m unittest discover -s runtime/tools -p 'test_*.py' -q
```

Builder menentukan sumber berdasarkan struktur repo; tidak mengambil skill global pengguna ketika struktur repo lengkap tersedia:

```bash
python3 runtime/tools/release.py --output-dir dist
python3 runtime/tools/release.py --check --output-dir dist
```

Builder memeriksa kesamaan reader runtime dan reader skill, sintaks Python, daftar sumber eksplisit, serta hash manifest arsip. `dist` tidak di-commit. Lisensi dan atribusi root disertakan pada arsip distribusi dari layout repo ini.

Pengujian akun nyata dilakukan terpisah dengan izin pengguna: priority, detail, history, material, lalu tindak lanjut memakai PDF yang sama. Bedakan waktu alat dari waktu keseluruhan agent. Pengujian protocol MCP tidak membuktikan bahwa model mengikuti skill; pembacaan dari cache juga bukan bukti sumber baru saja diperbarui.

Status pengembangan: pembacaan nyata native Codex dan integrasi protocol MCP Claude Code berhasil. Uji percakapan penuh Claude belum lulus karena akses model tidak tersedia; sesi CLI Codex terpisah mengalami penolakan model default. Tidak mengubah pengaturan model global untuk menyembunyikan batas tersebut. Pemasangan bersih di Mac lain masih perlu diuji.
