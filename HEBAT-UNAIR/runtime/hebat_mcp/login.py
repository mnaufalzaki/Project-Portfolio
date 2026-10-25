#!/usr/bin/env python3
"""Explicit interactive enrollment/update; persistent secrets go only to Keychain."""
import auth
if __name__=='__main__':
    try:
        auth.setup()
    except (auth.AuthError,auth.KeychainError) as e:
        print('Pengaturan belum selesai:',e.code)
        raise SystemExit(1)
