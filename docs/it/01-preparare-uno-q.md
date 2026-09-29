# 1. Preparare la UNO Q

Una Arduino UNO Q nuova di fabbrica ha bisogno di qualche passaggio prima che si possa installare DomotiQ: una password per l'utente `arduino`, un nome, una connessione di rete, SSH funzionante, un aggiornamento del sistema e l'accesso con chiave dal tuo PC. Questo capitolo ripercorre il modo in cui è stata preparata la prima casa (`casa1`), con qualche nota sulle sorprese incontrate lungo la strada.

La prima configurazione si può fare con Arduino App Lab (imposta nome, password e Wi-Fi, e prepara anche SSH e il nome `.local`) oppure a mano da una shell. I passi qui sotto sono quelli manuali; se hai usato App Lab, salta ad [Accesso con chiave SSH da un PC](#7-accesso-con-chiave-ssh-da-un-pc) e, se qualcosa non funziona, controlla le sezioni su SSH e avahi.

## Cosa serve

- Una Arduino UNO Q 4GB. DomotiQ è provato sull'immagine di fabbrica del 10 dicembre 2025 (Debian 13 "trixie"), aggiornata come descritto più avanti.
- Un PC con `adb` (Android platform tools) per la prima shell, e un cavo USB-C.
- Una rete Wi-Fi con accesso a internet. La scheda ha bisogno di internet per l'aggiornamento del sistema e, una volta sola, per l'installazione di DomotiQ.
- Sul PC, una copia del repository (per `scripts/add-pc.sh` e `scripts/release.sh`):

  ```bash
  git clone https://github.com/destone28/DomotiQ
  ```

## 1. Aprire una shell

Collega la scheda al PC con il cavo USB-C e apri una shell sulla scheda:

```bash
adb shell
```

## 2. Impostare la password dell'utente `arduino`

Sull'immagine di fabbrica l'utente `arduino` non ha una password. Impostane una con lo script di prima configurazione dell'immagine:

```bash
/usr/local/bin/arduino-passwd
```

È la password che ti chiederanno `sudo`, SSH e `scripts/add-pc.sh`.

## 3. Nome e fuso orario

Dai alla scheda il nome della sua casa (`casa1` o `casa2`) e il fuso orario italiano. L'installer li imposta di nuovo più avanti, ma il nome serve già adesso perché `casa1.local` funzioni.

```bash
arduino-app-cli system set-name casa1      # or: sudo hostnamectl set-hostname casa1
sudo timedatectl set-timezone Europe/Rome
```

## 4. Collegarsi al Wi-Fi del laboratorio

Durante lo sviluppo la scheda sta sulla tua normale rete Wi-Fi. Con NetworkManager:

```bash
sudo nmcli device wifi connect "YOUR-NETWORK" password "YOUR-PASSWORD"
```

## 5. Far funzionare SSH

Su un'immagine nuova SSH non parte: il log dice `sshd: no hostkeys available`. App Lab crea le chiavi host durante la sua prima configurazione; senza App Lab, creale tu:

```bash
sudo ssh-keygen -A
sudo systemctl restart ssh
```

## 6. Attivare avahi (il nome `.local`)

Sull'immagine di fabbrica `avahi-daemon` è spento (App Lab lo accende quando usi la sua modalità di rete). Senza avahi, dal PC `casa1.local` non si risolve.

```bash
sudo systemctl enable --now avahi-daemon
```

Adesso dal PC `ping casa1.local` dovrebbe rispondere. Anche l'installer attiva avahi, quindi il nome continua a funzionare dopo l'installazione.

## 7. Accesso con chiave SSH da un PC

Sul PC, dalla cartella del repository:

```bash
bash scripts/add-pc.sh casa1              # the board is on the lab network (casa1.local)
bash scripts/add-pc.sh casa1 10.42.1.1    # the board is on its own hotspot
```

Lo script:

1. crea la chiave `~/.ssh/id_ed25519_domotiq`, se questo PC non ce l'ha ancora;
2. la copia sulla scheda con `ssh-copy-id` (chiede una volta la password di `arduino`);
3. aggiunge una voce `Host casa1` a `~/.ssh/config` (utente `arduino`, quella chiave e l'indirizzo che hai indicato, oppure `casa1.local`);
4. si collega una volta e stampa `connected to casa1`.

Da qui in poi `ssh casa1` entra senza password. La voce viene aggiunta solo se `~/.ssh/config` non contiene già `Host casa1`: per far puntare un alias esistente a un altro indirizzo, modifica quel file.

Lancia lo stesso script su ogni altro PC che deve raggiungere la casa. In alternativa si può entrare con App Lab in modalità di rete.

## 8. Aggiornare il sistema

Entra con `ssh casa1` e lancia l'aggiornamento **come utente `arduino`, senza `sudo`**:

```bash
arduino-app-cli system update
```

`arduino-app-cli` si rifiuta di funzionare come root e chiama da solo `sudo apt-get`.

Lancialo da una sessione SSH. Dentro una `adb shell` l'aggiornamento si interrompe se la sessione adb si chiude; se non hai alternative, avvialo staccato con `systemd-run --uid=arduino`.

Su `casa1` l'aggiornamento ha portato `arduino-app-cli` 0.13.0, `arduino-cli` 1.5.1, il kernel Linux 7.0 e il core del microcontrollore `arduino:zephyr` 1.0.0, che è la versione usata da DomotiQ. Quando ha finito, riavvia, così entra in uso il nuovo kernel:

```bash
sudo reboot
```

### Se l'aggiornamento si ferma su una dipendenza ALSA

Sull'immagine di fabbrica l'aggiornamento può fermarsi con:

```
alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)
```

L'immagine prende i profili audio, il kernel, il firmware e mesa da `trixie-backports`, ma non la libreria ALSA che serve ai nuovi profili audio. Installa anche la libreria da backports, poi ripeti l'aggiornamento:

```bash
sudo apt-get install -y -t trixie-backports libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf
arduino-app-cli system update
```

`scripts/install.sh` applica la stessa correzione, quindi sulle schede che installerai in seguito se ne occupa lui.

## 9. Controllare lo spazio libero

Su `casa1` la partizione di sistema aveva circa 2 GB liberi su 9,8 GB, mentre `/home/arduino` è una partizione separata con circa 15 GB liberi. DomotiQ vive in `/home/arduino/domotiq`, quindi quella che conta è la partizione home:

```bash
df -h /home/arduino
```

Una prima installazione ha bisogno di circa 2,3 GB lì; l'installer lo controlla prima di cominciare.

## Prima che la casa vada in fiera

Quando lo sviluppo è finito:

- permetti l'accesso SSH solo con chiave (per esempio `PasswordAuthentication no` in un file dentro `/etc/ssh/sshd_config.d/`, poi `sudo systemctl restart ssh`), dopo aver controllato che la tua chiave funzioni;
- se durante lo sviluppo hai dato all'utente `arduino` un `sudo` senza password, rimetti la password a `sudo` (la piccola regola installata da DomotiQ, che permette solo di riavviare i suoi servizi, riavviare o spegnere la scheda e cambiare l'hotspot, può restare);
- scrivi la password del Wi-Fi e il PIN dello staff sulla copia stampata della [guida rapida per lo staff](guida-rapida-staff.md), mai nel repository.

Avanti: [installare il software](02-installazione.md).
