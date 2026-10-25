"""Native macOS Keychain bridge. Secrets stay in memory, never in argv or output."""
import ctypes as C
import json
import sys

class KeychainError(RuntimeError):
    def __init__(self,status):
        self.status=int(status)
        names={-25300:'item_not_found',-25308:'keychain_locked_or_permission_required',-128:'user_cancelled',-25293:'authentication_failed'}
        self.code=names.get(self.status,'keychain_operation_failed')
        super().__init__(self.code)

class KeychainStore:
    def __init__(self,service='id.ac.unair.hebat.codex'):
        if sys.platform!='darwin':raise RuntimeError('macOS Keychain diperlukan.')
        self.service=service
        self.cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.sec=C.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.cf.CFStringCreateWithCString.argtypes=[C.c_void_p,C.c_char_p,C.c_uint32];self.cf.CFStringCreateWithCString.restype=C.c_void_p
        self.cf.CFDataCreate.argtypes=[C.c_void_p,C.c_void_p,C.c_long];self.cf.CFDataCreate.restype=C.c_void_p
        self.cf.CFDictionaryCreateMutable.argtypes=[C.c_void_p,C.c_long,C.c_void_p,C.c_void_p];self.cf.CFDictionaryCreateMutable.restype=C.c_void_p
        self.cf.CFDictionarySetValue.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p]
        self.cf.CFDataGetLength.argtypes=[C.c_void_p];self.cf.CFDataGetLength.restype=C.c_long
        self.cf.CFDataGetBytePtr.argtypes=[C.c_void_p];self.cf.CFDataGetBytePtr.restype=C.c_void_p
        self.cf.CFRelease.argtypes=[C.c_void_p]
        for name,nargs in [('SecItemCopyMatching',2),('SecItemAdd',2),('SecItemUpdate',2),('SecItemDelete',1)]:
            fn=getattr(self.sec,name);fn.argtypes=[C.c_void_p]*nargs;fn.restype=C.c_int32
        self.sec.SecKeychainSetUserInteractionAllowed.argtypes=[C.c_bool];self.sec.SecKeychainSetUserInteractionAllowed.restype=C.c_int32
    def symbol(self,name):return C.c_void_p.in_dll(self.sec,name).value
    def string(self,s):return self.cf.CFStringCreateWithCString(None,s.encode(),0x08000100)
    def dictionary(self,values):
        # CF callbacks retain keys and values; local temporary references are released.
        kp=C.c_byte.in_dll(self.cf,'kCFTypeDictionaryKeyCallBacks')
        vp=C.c_byte.in_dll(self.cf,'kCFTypeDictionaryValueCallBacks')
        d=self.cf.CFDictionaryCreateMutable(None,0,C.byref(kp),C.byref(vp))
        for key,value in values.items():self.cf.CFDictionarySetValue(d,self.symbol(key),value)
        return d
    def query(self,account):
        serv=self.string(self.service);acct=self.string(account)
        d=self.dictionary({'kSecClass':self.symbol('kSecClassGenericPassword'),'kSecAttrService':serv,'kSecAttrAccount':acct})
        self.cf.CFRelease(serv);self.cf.CFRelease(acct)
        return d
    def read(self,account,interactive=False):
        self.sec.SecKeychainSetUserInteractionAllowed(interactive)
        q=self.query(account);result=C.c_void_p()
        self.cf.CFDictionarySetValue(q,self.symbol('kSecReturnData'),C.c_void_p.in_dll(self.cf,'kCFBooleanTrue').value)
        try:
            status=self.sec.SecItemCopyMatching(q,C.byref(result))
            if status==-25300:return None
            if status:raise KeychainError(status)
            data=C.string_at(self.cf.CFDataGetBytePtr(result),self.cf.CFDataGetLength(result))
            try:return json.loads(data)
            except (ValueError,UnicodeError):raise RuntimeError('keychain_item_format_invalid') from None
        finally:
            if result.value:self.cf.CFRelease(result)
            self.cf.CFRelease(q)
    def write(self,account,value,interactive=False):
        self.sec.SecKeychainSetUserInteractionAllowed(interactive)
        payload=json.dumps(value,separators=(',',':')).encode()
        buf=C.create_string_buffer(payload);data=self.cf.CFDataCreate(None,C.cast(buf,C.c_void_p),len(payload))
        query=self.query(account);attrs=self.dictionary({'kSecValueData':data})
        try:
            status=self.sec.SecItemUpdate(query,attrs)
            if status==-25300:
                self.cf.CFDictionarySetValue(query,self.symbol('kSecValueData'),data)
                status=self.sec.SecItemAdd(query,None)
            if status:raise KeychainError(status)
        finally:
            self.cf.CFRelease(attrs);self.cf.CFRelease(query);self.cf.CFRelease(data)
    def delete(self,account,interactive=False):
        self.sec.SecKeychainSetUserInteractionAllowed(interactive)
        query=self.query(account)
        try:
            status=self.sec.SecItemDelete(query)
            if status not in (0,-25300):raise KeychainError(status)
        finally:self.cf.CFRelease(query)
