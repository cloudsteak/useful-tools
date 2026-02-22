# SSH Útmutató Kezdőknek

> Biztonságos kapcsolódás szerverekhez SSH kulcsokkal – lépésről lépésre, magyarul

---

## Mi az SSH és miért használjuk?

Az **SSH (Secure Shell)** egy titkosított protokoll, amellyel biztonságosan csatlakozhatunk távoli szerverekhez. Képzeld el úgy, mint egy titkosított telefon vonalat: senki nem hallgathatja le a kommunikációt.

Az SSH kulcspáros hitelesítés sokkal biztonságosabb, mint a jelszavas bejelentkezés, mert:
- Nem kell jelszót gépelni (és nem lehet ellopni)
- Matematikailag szinte feltörhetetlen
- A szerver soha nem látja a privát kulcsodat

---

## A kulcspár logikája – Egy egyszerű analógia

Gondolj egy **lakatot és egy kulcsra**:

| Analógia | SSH megfelelője | Hol van? |
|----------|----------------|-----------|
| 🔑 Fizikai kulcs | **Privát kulcs** (`id_ed25519`) | Csak a te gépeden! |
| 🔒 Lakat | **Publikus kulcs** (`id_ed25519.pub`) | A szerveren |

A **publikus kulcsot** bátran megoszthatod bárkivel – a szerverre feltöltöd, és az fogja "tartani" a lakatot. A **privát kulcs** soha ne hagyja el a gépedet – ez nyitja ki a lakatot. Ha valaki megszerzi a privát kulcsodat, hozzáférhet minden olyan szerverhez, ahova az tartozó publikus kulcsot feltöltötted.

⚠️ **Privát kulcs = digitális személyazonosság. Soha ne oszd meg senkivel, ne töltsd fel sehova!**

---

## 🪟 Windows 11

### 1. SSH kulcs generálása Windows 11-en

#### Előfeltételek: OpenSSH ellenőrzése

Windows 11-en az OpenSSH kliens jellemzően alapból elérhető. Ellenőrizzük:

Nyisd meg a **PowerShell**-t rendszergazdaként (jobb klikk → "Futtatás rendszergazdaként"):

```powershell
# Ellenőrzés: telepítve van-e az OpenSSH kliens
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Client*'
```

Ha a kimenet ezt mutatja, minden rendben:
```
Name  : OpenSSH.Client~~~~0.0.1.0
State : Installed
```

Ha `NotPresent` állapotot látsz, telepítsd:

```powershell
# OpenSSH kliens telepítése (rendszergazdai PowerShell szükséges)
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

Ellenőrizd a telepítést:

```powershell
# SSH verzió ellenőrzése – ha ez kiír valamit, működik
ssh -V
```

Várható kimenet (verzió eltérhet):
```
OpenSSH_for_Windows_9.5p1, LibreSSL 3.8.2
```

---

#### SSH kulcs generálása

**Ajánlott: ED25519 kulcs** (gyorsabb, biztonságosabb, kisebb méretű)

Nyiss egy normál PowerShell ablakot (nem kell rendszergazda):

```powershell
# ED25519 kulcspár generálása – ez az ajánlott módszer
ssh-keygen -t ed25519 -C "email@example.com"
```

A `-C` után írd a saját email címedet – ez egy komment, ami segít azonosítani a kulcsot később.

A parancs futtatása után kérdéseket tesz fel:

```
Enter file in which to save the key ($env:USERPROFILE/.ssh/id_ed25519):
```
➡️ Nyomj **Enter**-t az alapértelmezett helyre való mentéshez.

```
Enter passphrase (empty for no passphrase):
```
➡️ Adj meg egy jelszót (erősen ajánlott!), vagy nyomj **Enter**-t jelszó nélkül.

> 💡 **Passphrase (jelmondat):** Ez egy extra védelmi réteg – még ha valaki megszerzi a privát kulcs fájlját, ezt a jelszót is tudnia kell. Erősen ajánlott beállítani!

```
Enter same passphrase again:
```
➡️ Add meg újra a jelszót.

**Alternatíva: RSA 4096 kulcs** (régebbi rendszerekkel való kompatibilitáshoz)

```powershell
# RSA 4096 kulcspár generálása – csak akkor, ha az ED25519 nem működik valahol
ssh-keygen -t rsa -b 4096 -C "email@example.com"
```

---

#### Ahol a fájlok tárolódnak

A kulcsaid alapból itt lesznek:

```
$env:USERPROFILE\.ssh\
├── id_ed25519        ← Ez a PRIVÁT kulcs (soha ne oszd meg!)
├── id_ed25519.pub    ← Ez a PUBLIKUS kulcs (ezt töltöd fel a szerverre)
└── known_hosts       ← Ismert szerverek listája (automatikusan kezeli az SSH)
```

A `.pub` kiterjesztésű fájl tartalma valahogy így néz ki:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... email@example.com
```

Ez teljesen publikus adat – ezt másolod a szerverre.

---

### 2. Kapcsolódás és privát kulcs kezelés Windows 11-en (OpenSSH)

Ha az `ssh` parancs működik a PowerShell-ben, **nincs szükség PuTTY-re**. A Windows beépített OpenSSH kliensével ugyanazokat a feladatokat meg tudod oldani.

Ha a célgép Linux szerver, akkor a bejelentkezéshez a publikus kulcsodnak szerepelnie kell a szerveren az `~/.ssh/authorized_keys` fájlban. Ezt a dokumentum későbbi részében, a **„🔑 Közös” → „Publikus kulcs feltöltése a szerverre”** fejezetben leírt lépésekkel tudod megcsinálni.

---

#### Privát kulcs biztonságos tárolása Windows 11-en

A privát kulcs alapból itt van:

`$env:USERPROFILE\.ssh\id_ed25519`

Ezt a fájlt csak a saját felhasználód olvashassa. Ha túl nyitott a jogosultság, az SSH megtagadhatja a használatát.

PowerShell-ben ellenőrizheted és szigoríthatod az ACL jogosultságokat:

```powershell
# Öröklés kikapcsolása és csak a saját felhasználónak olvasási jog
icacls $env:USERPROFILE\.ssh\id_ed25519 /inheritance:r
icacls $env:USERPROFILE\.ssh\id_ed25519 /grant:r "$($env:USERNAME):(R)"
```

Ha publikus kulcsot újragenerálsz, a `.pub` fájl megosztható, de a privát kulcs (`id_ed25519`) soha.

---

#### `ssh-agent` használata (hogy ne kelljen mindig passphrase-t írni)

Az `ssh-agent` biztonságosan memóriában tartja a feloldott kulcsot a munkamenet idejére.

```powershell
# Szolgáltatás engedélyezése automatikus indulásra (egyszer kell)
Set-Service -Name ssh-agent -StartupType Automatic

# Szolgáltatás indítása
Start-Service ssh-agent

# Kulcs betöltése az agentbe
ssh-add $env:USERPROFILE\.ssh\id_ed25519

# Betöltött kulcsok listázása
ssh-add -l
```

> 💡 Ha újraindítás után nem indulna automatikusan, futtasd újra a `Start-Service ssh-agent` parancsot.

---

#### Kapcsolódás PowerShell-ből (beépített `ssh`)

```powershell
# Alap kapcsolódás – felhasználónév@szerver
ssh felhasznalonev@192.168.1.100

# Kapcsolódás specifikus kulccsal
ssh -i $env:USERPROFILE\.ssh\id_ed25519 felhasznalonev@szerver.example.com

# Kapcsolódás más porton
ssh -p 2222 felhasznalonev@szerver.example.com
```

---

#### Opcionális: Windows SSH config használata

Hozd létre (vagy szerkeszd) ezt a fájlt:

`$env:USERPROFILE\.ssh\config`

Példa:

```
Host munka
    HostName szerver.example.com
    User felhasznalonev
    IdentityFile ~/.ssh/id_ed25519
    Port 22

Host teszt
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519
    Port 2222
```

Ezután elég ennyi:

```powershell
ssh munka
ssh teszt
```

---

## 🍎🐧 Mac / Linux

### 1. SSH kulcs generálása Mac/Linux-on

#### Előfeltételek

A Mac és Linux rendszereken az SSH szinte mindig alapból elérhető. Ellenőrizd:

```bash
# SSH verzió ellenőrzése
ssh -V
```

Várható kimenet:
```
OpenSSH_9.7p1, LibreSSL 3.3.6
```

Ha a parancs nem található, Linux-on telepítsd:

```bash
# Ubuntu/Debian rendszereken
sudo apt install openssh-client

# Fedora/RHEL rendszereken
sudo dnf install openssh-clients
```

---

#### SSH kulcs generálása

Nyiss egy **Terminal** ablakot és futtasd:

**Ajánlott: ED25519 kulcs**

```bash
# ED25519 kulcspár generálása – ajánlott kezdőknek és haladóknak egyaránt
ssh-keygen -t ed25519 -C "email@example.com"
```

A parancs futtatása után:

```
Enter file in which to save the key (/home/felhasznalo/.ssh/id_ed25519):
```
➡️ Nyomj **Enter**-t az alapértelmezett helyre való mentéshez.

```
Enter passphrase (empty for no passphrase):
```
➡️ Adj meg egy erős jelszót, majd ismételd meg. (Vagy Enter a jelszó nélküli verzióhoz, de ez nem ajánlott!)

**Alternatíva: RSA 4096 kulcs**

```bash
# RSA 4096 kulcspár generálása – régi rendszerekkel való kompatibilitáshoz
ssh-keygen -t rsa -b 4096 -C "email@example.com"
```

---

#### Jogosultságok beállítása

Ez **kritikusan fontos**! Az SSH biztonsági okokból megtagadja a kapcsolatot, ha a kulcsfájlok jogosultságai nem megfelelőek. Az SSH azt mondja: "Ha más is hozzáférhet a kulcsodhoz, nem bízom benne."

```bash
# A .ssh mappa legyen csak a tiéd (olvasható és írható csak neked)
chmod 700 ~/.ssh

# A privát kulcs legyen csak általad olvasható – mások ne lássák!
# AWS környezetben gyakran a 400 az elvárt (pl. .pem kulcsoknál)
chmod 400 ~/.ssh/id_ed25519

# Alternatíva: 600 is elfogadott sok rendszeren (tulajdonos írhatja is)
# chmod 600 ~/.ssh/id_ed25519

# A publikus kulcs olvasható lehet mások által is
chmod 644 ~/.ssh/id_ed25519.pub

# Az authorized_keys fájl jogosultsága
chmod 600 ~/.ssh/authorized_keys
```

⚠️ **Ha ezeket nem állítod be**, az SSH hibát dob és nem fog csatlakozni:
```
WARNING: UNPROTECTED PRIVATE KEY FILE!
Permissions 0644 for '/home/user/.ssh/id_ed25519' are too open.
```

---

#### Fájlok helye és magyarázata

```
~/.ssh/                         ← Az SSH "otthona" (~ = home mappád)
├── id_ed25519                  ← Privát kulcs – SOHA ne oszd meg!
├── id_ed25519.pub              ← Publikus kulcs – ezt töltöd fel a szerverre
├── known_hosts                 ← Ismert szerverek és ujjlenyomataik
├── authorized_keys             ← (Szerveren) Engedélyezett publikus kulcsok
└── config                      ← SSH beállítások (opcionális, de nagyon hasznos)
```

---

### 2. SSH kapcsolódás Mac/Linux-on

#### Alap kapcsolódás

```bash
# Kapcsolódás szerverre: ssh felhasználónév@szerver
ssh felhasznalonev@192.168.1.100

# Ha a helyi felhasználóneved megegyezik a szerverével, elég ez:
ssh szerver.example.com
```

Az első kapcsolódáskor ezt látod:

```
The authenticity of host '192.168.1.100 (192.168.1.100)' can't be established.
ED25519 key fingerprint is SHA256:abc123...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

➡️ Írd be: `yes` – ez elmenti a szerver ujjlenyomatát a `known_hosts` fájlba, hogy legközelebb ne kérdezze.

> 💡 Ideális esetben valaki más (pl. a rendszergazda) megadja előre a szerver ujjlenyomatát, és te azt ellenőrzöd. Ez véd a "man-in-the-middle" támadástól.

---

#### Specifikus kulcs megadása `-i` flaggel

Ha több kulcsod van, megmondhatod, melyiket használja:

```bash
# Specifikus kulcs használata – hasznos ha több kulcsod van
ssh -i ~/.ssh/id_ed25519 felhasznalonev@szerver.example.com

# Másik kulcs (pl. munkához külön kulcs)
ssh -i ~/.ssh/work_key felhasznalonev@munka-szerver.com
```

---

#### Az `~/.ssh/config` fájl – Az SSH "gyorsgombjai"

A config fájl lehetővé teszi, hogy hosszú `ssh` parancsok helyett egyszerű aliasokat használj. Egyszer kell beállítani, utána örökké egyszerűbb az élet.

**Config fájl létrehozása/szerkesztése:**

```bash
# Config fájl megnyitása szerkesztésre (ha nem létezik, létrehozza)
nano ~/.ssh/config
```

**Példa config fájl tartalma:**

```
# Munka szerver
Host munka
    HostName szerver.example.com
    User felhasznalonev
    IdentityFile ~/.ssh/id_ed25519
    Port 22

# Teszt szerver más porton
Host teszt
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/teszt_kulcs
    Port 2222

# Alapértelmezett beállítások minden kapcsolathoz
Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

**Mentés és kilépés nano-ból:** `Ctrl+O`, Enter, `Ctrl+X`

**Jogosultság beállítása:**

```bash
# A config fájl jogosultsága
chmod 600 ~/.ssh/config
```

**Ezután már csak ennyit kell gépelni:**

```bash
# Ahelyett hogy: ssh -i ~/.ssh/id_ed25519 felhasznalonev@szerver.example.com -p 22
ssh munka

# Ahelyett hogy: ssh -i ~/.ssh/teszt_kulcs ubuntu@192.168.1.100 -p 2222
ssh teszt
```

---

## 🔑 Közös

### Publikus kulcs feltöltése a szerverre

Mielőtt kulcsos bejelentkezést használhatsz, a publikus kulcsodat (`id_ed25519.pub` tartalmát) hozzá kell adni a szerveren az `~/.ssh/authorized_keys` fájlhoz.

> ⚠️ **Fontos:** Ehhez először be kell tudni jelentkezni a szerverre (jelszóval vagy más módon). Kérd meg a rendszergazdát, ha nincs kezdeti hozzáférésed!

---

#### 1. módszer: Manuális módszer (minden OS-en működik)

Ez a biztos alap módszer, ha közvetlenül akarod szerkeszteni az `authorized_keys` fájlt.

**Lépés 1: Nézd meg a publikus kulcsodat**

Windows (PowerShell):
```powershell
# Publikus kulcs tartalmának megjelenítése
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

Mac/Linux:
```bash
# Publikus kulcs tartalmának megjelenítése
cat ~/.ssh/id_ed25519.pub
```

Kimenet (valami hasonló):
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAbCdEfGh... email@example.com
```

**Lépés 2: Másold ki a teljes sort** (Ctrl+C / Cmd+C)

**Lépés 3: Jelentkezz be a szerverre** (jelszóval)

```bash
ssh felhasznalonev@szerver.example.com
```

**Lépés 4: Hozd létre az `authorized_keys` fájlt (ha még nincs) és add hozzá a kulcsot**

```bash
# .ssh mappa létrehozása, ha még nincs
mkdir -p ~/.ssh

# Jogosultság beállítása
chmod 700 ~/.ssh

# Kulcs hozzáadása az authorized_keys fájlhoz (>> nem felülírja, hanem hozzáfűzi!)
echo "ide_illeszd_be_a_teljes_publikus_kulcsot" >> ~/.ssh/authorized_keys

# Jogosultság beállítása
chmod 600 ~/.ssh/authorized_keys
```

⚠️ **Ügyelj:** Az `echo` után pontosan azt a sort illeszd be, amit a publikus kulcs fájlból kimásoltál, idézőjelbe téve.

**Lépés 5: Teszteld a kapcsolatot új terminálablakból!**

> 💡 Ne zárd be a jelenlegi munkamenetet amíg nem teszteltél! Ha valamit elrontasz, így még vissza tudsz lépni jelszóval és javítani.

---

#### 2. módszer: `ssh-copy-id` (gyorsabb – Mac/Linux)

Ha elérhető az `ssh-copy-id`, ugyanazt automatikusan elvégzi:

```bash
# Publikus kulcs másolása a szerverre egy paranccsal
ssh-copy-id -i ~/.ssh/id_ed25519.pub felhasznalonev@szerver.example.com
```

Ha a szerver nem a 22-es portot használja:

```bash
# Más port megadása
ssh-copy-id -i ~/.ssh/id_ed25519.pub -p 2222 felhasznalonev@szerver.example.com
```

A parancs jelszót kér (jelszavas bejelentkezéssel), majd automatikusan hozzáadja a kulcsot. Ezután már kulccsal tudsz belépni!

---

#### 3. módszer: Egysoros pipe módszer (Mac/Linux)

Ha nem akarod manuálisan másolni a kulcsot, ezt az egyetlen parancsot futtathatod:

```bash
# Egy paranccsal: kulcs másolása SSH-n keresztül
cat ~/.ssh/id_ed25519.pub | ssh felhasznalonev@szerver.example.com "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Ez a parancs:
1. Kiolvassa a publikus kulcsot
2. SSH-n keresztül átadja a szervernek
3. A szerveren létrehozza a szükséges mappát (ha nincs)
4. Hozzáfűzi a kulcsot az `authorized_keys` fájlhoz
5. Beállítja a jogosultságokat

---

### Melyik kulcsot használta a bejelentkezéskor?

Több kulcs esetén hasznos tudni, melyiket fogadta el a szerver. Íme a diagnosztikai eszközök:

---

#### SSH verbose mód: `ssh -v`

A verbose mód részletes naplót ír ki a kapcsolódás folyamatáról. Látod, melyik kulcsokat próbálta és melyik működött.

```bash
# Verbose mód – részletes kapcsolódási napló
ssh -v felhasznalonev@szerver.example.com
```

Keress ilyen sorokat a kimenetben:

```
debug1: Trying private key: /home/user/.ssh/id_ed25519
debug1: Server accepts key: /home/user/.ssh/id_ed25519 ED25519 SHA256:abc123...
debug1: Authentication succeeded (publickey).
```

Ha még több részletet szeretnél (haladó hibakereséshez):

```bash
# Még részletesebb napló (-vv vagy -vvv)
ssh -vv felhasznalonev@szerver.example.com
```

---

#### Szerver oldali log ellenőrzése

Ha hozzáférsz a szerverhez, megnézheted a bejelentkezési naplókat:

```bash
# Modern Linux rendszereken (systemd) – utolsó 50 sor
journalctl -u ssh -n 50

# Régebbi rendszereken vagy Ubuntu-n
sudo tail -50 /var/log/auth.log

# Debian/Ubuntu – SSH specifikus bejegyzések szűrése
sudo grep "Accepted publickey" /var/log/auth.log
```

Keress ilyen sort:

```
Feb 22 10:15:32 szerver sshd[1234]: Accepted publickey for felhasznalonev from 192.168.1.50 port 54321 ssh2: ED25519 SHA256:abc123...
```

Ez megmutatja:
- Mikor volt a bejelentkezés
- Melyik felhasználó lépett be
- Honnan (IP cím)
- Milyen kulcstípussal és ujjlenyomattal

---

#### Fingerprint (ujjlenyomat) azonosítása

Minden kulcsnak van egy "ujjlenyomata" – egy rövid azonosító string. Ezzel azonosíthatod, melyik kulcs melyik.

```bash
# Saját kulcs ujjlenyomatának megjelenítése
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

Kimenet:
```
256 SHA256:abc123xyz... email@example.com (ED25519)
```

```bash
# Privát kulcs ujjlenyomata (ugyanaz lesz)
ssh-keygen -lf ~/.ssh/id_ed25519

# Authorized_keys fájlban lévő kulcsok ujjlenyomatai (szerveren)
ssh-keygen -lf ~/.ssh/authorized_keys
```

Hasonlítsd össze az ujjlenyomatot a szerver naplójában látottal – ha egyezik, megtaláltad!

---

#### Authorized_keys kommentelés több kulcsnál

Ha több kulcsot adsz hozzá az `authorized_keys` fájlhoz, érdemes kommentekkel ellátni őket, hogy tudd, melyik kié:

```bash
# Authorized_keys fájl tartalma szerveren – jól kommentelt példa
cat ~/.ssh/authorized_keys
```

Így nézhet ki egy jól szervezett `authorized_keys` fájl:

```
# Otthoni laptop - Kovács János - 2024-01-15
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... janos@otthon

# Munkahelyi gép - Kovács János - 2024-02-01
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5BBBB... janos@munka

# CI/CD rendszer - GitHub Actions - 2024-03-10
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5CCCC... github-actions
```

> 💡 A `#` kezdetű sorok kommentek – az SSH figyelmen kívül hagyja őket, de neked segítenek eligazodni.

Ha le akarod tiltani egy kulcsot anélkül, hogy törölnéd, egy `#`-et rakj elé:

```bash
# Szerkeszd az authorized_keys fájlt
nano ~/.ssh/authorized_keys
```

```
# Letiltva 2024-04-01 - régi laptop ellopva
# ssh-ed25519 AAAAC3NzaC1lZDI1NTE5DDDD... regi-laptop
```

---

### ED25519 vs RSA – Melyiket válasszam?

| Szempont | ED25519 | RSA 4096 |
|----------|---------|----------|
| **Biztonság** | ✅ Nagyon erős (modern matematika) | ✅ Erős (ha 4096 bit) |
| **Kulcsméret** | ✅ Kicsi (~68 karakter) | ❌ Nagy (~700 karakter) |
| **Sebesség** | ✅ Gyors aláírás és ellenőrzés | ❌ Lassabb |
| **Kompatibilitás** | ✅ Modern rendszerek (2014+) | ✅ Minden rendszer |
| **Kvantumellenállás** | ⚠️ Nem jobban, mint az RSA | ⚠️ Nem kvantumellenálló |
| **Ajánlott** | ✅ **Igen – ez a jövő** | Csak ha muszáj |

#### Mikor kell még RSA?

Néhány régi rendszer vagy szoftver nem támogatja az ED25519-et:
- Nagyon régi SSH szerverek (OpenSSH 6.4 előtti, 2013 előtt)
- Néhány hálózati eszköz (routerek, switchek régi firmware-rel)
- Egyes enterprise rendszerek (pl. régi Cisco eszközök)
- Bizonyos legacy alkalmazások

#### Ajánlás kezdőknek

**Mindig ED25519-et használj**, hacsak valaki kifejezetten RSA-t nem kér. Ha RSA-t kell, mindig `4096` bites legyen – az `rsa 2048` mára gyengének számít.

> 💡 Ha bizonytalan vagy, generálhatsz mindkettőt és kezelheted mindkét kulcsot párhuzamosan – a szerverre mindkét publikus kulcsot feltöltheted az `authorized_keys` fájlba.

---

## Gyors referencia – Leggyakoribb parancsok

```bash
# Kulcs generálása (ED25519 – ajánlott)
ssh-keygen -t ed25519 -C "email@example.com"

# Kulcs generálása (RSA – kompatibilitáshoz)
ssh-keygen -t rsa -b 4096 -C "email@example.com"

# Publikus kulcs megjelenítése (ezt töltöd fel a szerverre)
cat ~/.ssh/id_ed25519.pub

# Kulcs ujjlenyomatának megjelenítése
ssh-keygen -lf ~/.ssh/id_ed25519.pub

# Publikus kulcs másolása szerverre (legegyszerűbb)
ssh-copy-id -i ~/.ssh/id_ed25519.pub felhasznalonev@szerver

# Kapcsolódás
ssh felhasznalonev@szerver

# Kapcsolódás specifikus kulccsal
ssh -i ~/.ssh/id_ed25519 felhasznalonev@szerver

# Kapcsolódás részletes naplóval (hibakereséshez)
ssh -v felhasznalonev@szerver

# Szerveren: bejelentkezési napló ellenőrzése
journalctl -u ssh -n 50
sudo grep "Accepted publickey" /var/log/auth.log
```

---

## Hibaelhárítás – Leggyakoribb problémák

### "Permission denied (publickey)"

Ez a leggyakoribb hiba. Lehetséges okok:

1. **A publikus kulcs nincs a szerveren** → Töltsd fel az `authorized_keys` fájlba
2. **Rossz jogosultságok** → Ellenőrizd: `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`
3. **Rossz felhasználónév** → Ellenőrizd a szerver felhasználónevét
4. **Jelszavas bejelentkezés le van tiltva** → Kérd meg a rendszergazdát

**Diagnosztika:**
```bash
# Részletes napló a hibáról
ssh -v felhasznalonev@szerver
```

---

### "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!"

Ez azt jelenti, hogy a szerver ujjlenyomata megváltozott. Ez lehet:
- ✅ Jogos: a szerver újratelepítése után
- ⚠️ Veszélyes: esetleg "man-in-the-middle" támadás

Ha biztos vagy benne, hogy jogos a változás (pl. te telepítetted újra a szervert):

```bash
# Régi bejegyzés törlése a known_hosts-ból
ssh-keygen -R szerver.example.com
# vagy IP cím esetén:
ssh-keygen -R 192.168.1.100
```

Majd csatlakozz újra és fogadd el az új ujjlenyomatot.

---

### "Bad permissions" / "Permissions are too open"

```bash
# Javítsd a jogosultságokat
chmod 700 ~/.ssh

# Privát kulcs: AWS-hez tipikusan 400, általánosan 600 is jó
chmod 400 ~/.ssh/id_ed25519
# vagy:
# chmod 600 ~/.ssh/id_ed25519

chmod 644 ~/.ssh/id_ed25519.pub
chmod 600 ~/.ssh/authorized_keys
chmod 600 ~/.ssh/config
```

---

*Útmutató verziója: 1.0 | Utolsó frissítés: 2026-02-22*
