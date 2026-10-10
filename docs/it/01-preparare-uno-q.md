# 1. Preparare la UNO Q

Una Arduino UNO Q nuova di fabbrica ha bisogno di qualche passaggio prima che si possa installare DomotiQ: una password per l'utente `arduino`, un nome, una connessione di rete, SSH funzionante, un aggiornamento del sistema e l'accesso con chiave dal tuo PC. Questo capitolo li ripercorre in ordine, con qualche nota sulle sorprese che si possono incontrare.

In tutta la guida la scheda si chiama `casa1` e la password dell'utente `arduino` è `domotiq2026`. Se ne scegli altri, usa i tuoi al loro posto.

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

Sull'immagine di fabbrica l'utente `arduino` non ha una password: la chiede il primo comando con `sudo`. Lancia:

```bash
sudo -v
```

Quando la scheda chiede la password nuova, scrivi `domotiq2026`. È la password che ti chiederanno `sudo`, SSH e `scripts/add-pc.sh`.

## 3. Nome e fuso orario

Dai alla scheda il nome `casa1` e il fuso orario. L'installer li imposta di nuovo più avanti, ma il nome serve già adesso perché `casa1.local` funzioni. Se rinomini una scheda che ha già avahi acceso (passo 6), riavvialo perché annunci il nome nuovo: `sudo systemctl restart avahi-daemon`.

```bash
sudo hostnamectl set-hostname casa1
sudo timedatectl set-timezone Europe/Rome
```

## 4. Collegarsi al Wi-Fi

Durante la preparazione la scheda sta sulla tua normale rete Wi-Fi, la stessa del PC. Con NetworkManager:

```bash
sudo nmcli --ask device wifi connect "YOUR-NETWORK"
```

La password della rete si scrive quando `nmcli` la chiede: così non resta nella cronologia dei comandi.

## 5. Far funzionare SSH

Su un'immagine nuova SSH non parte: il log dice `sshd: no hostkeys available`, e il servizio non è nemmeno attivato all'avvio. App Lab crea le chiavi host durante la sua prima configurazione; senza App Lab, crea le chiavi e attiva il servizio, così parte anche dopo ogni riavvio:

```bash
sudo ssh-keygen -A
sudo systemctl enable --now ssh
```

Con il solo `restart` SSH funziona fino al primo riavvio, poi la scheda risponde solo via USB (`adb shell`): succede proprio dopo l'aggiornamento del passo 8. Anche l'installer attiva il servizio.

## 6. Attivare avahi (il nome `.local`)

Sull'immagine di fabbrica `avahi-daemon` è spento (App Lab lo accende quando usi la sua modalità di rete). Senza avahi, dal PC `casa1.local` non si risolve.

```bash
sudo systemctl enable --now avahi-daemon
```

Adesso dal PC `ping casa1.local` dovrebbe rispondere. Anche l'installer attiva avahi, quindi il nome continua a funzionare dopo l'installazione.

## 7. Accesso con chiave SSH da un PC

Con la scheda sulla stessa rete del PC, dalla cartella del repository sul PC:

```bash
bash scripts/add-pc.sh casa1
```

Se invece la scheda è già sul suo hotspot (dopo l'installazione) e il PC è collegato alla rete `DomotiQ-Casa1`, aggiungi l'indirizzo della casa:

```bash
bash scripts/add-pc.sh casa1 10.42.1.1
```

Lo script:

1. crea la chiave `~/.ssh/id_ed25519_domotiq`, se questo PC non ce l'ha ancora;
2. la copia sulla scheda con `ssh-copy-id`, che chiede una volta la password di `arduino` (`domotiq2026`);
3. aggiunge una voce `Host casa1` a `~/.ssh/config` (utente `arduino`, quella chiave e l'indirizzo che hai indicato, oppure `casa1.local`);
4. si collega una volta e stampa `connected to casa1`.

Da qui in poi `ssh casa1` entra senza password. La voce viene aggiunta solo se `~/.ssh/config` non contiene già `Host casa1`: se ne contiene una con un altro indirizzo, lo script lo dice, e per cambiarla si modifica quel file.

**Una scheda nuova con un nome già usato.** Ogni scheda ha una sua identità, creata al primo avvio, e il PC si ricorda quella di ogni nome. Se il PC conosceva già una `casa1` (una scheda reinstallata, o un'altra), lo script lo dice e chiede se dimenticare l'identità vecchia: rispondi `y`. Senza lo script, `ssh` si rifiuta con *REMOTE HOST IDENTIFICATION HAS CHANGED*; la soluzione è la stessa:

```bash
ssh-keygen -R casa1.local
```

Se la scheda non risponde, lo script stampa l'errore di rete e ricorda quale forma usare. Lancia lo stesso script su ogni altro PC che deve raggiungere la casa. In alternativa si può entrare con App Lab in modalità di rete.

## 8. Aggiornare il sistema

Entra con `ssh casa1`. Sull'immagine di fabbrica l'aggiornamento si fermerebbe su una dipendenza della libreria audio (vedi sotto): installa prima quella libreria da backports, poi lancia l'aggiornamento **come utente `arduino`, senza `sudo`**:

```bash
sudo apt-get install -y -t trixie-backports libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf
arduino-app-cli system update
```

`arduino-app-cli` si rifiuta di funzionare come root e chiama da solo `sudo apt-get`; con `--yes` non chiede conferme.

Lancialo da una sessione SSH. Dentro una `adb shell` l'aggiornamento si interrompe se la sessione adb si chiude; se non hai alternative, avvialo staccato con `systemd-run --uid=arduino`. Su una scheda nuova dura una mezz'ora: alla fine scarica anche le immagini Docker di App Lab, che DomotiQ non usa, e intanto la scheda può non rispondere in rete (vedi [Risoluzione dei problemi](11-risoluzione-problemi.md)).

Durante la preparazione del progetto l'aggiornamento ha portato `arduino-app-cli` 0.13.0, `arduino-cli` 1.5.1, il kernel Linux 7.0 e il core del microcontrollore `arduino:zephyr` 1.0.0, che è la versione usata da DomotiQ. Quando ha finito, riavvia, così entra in uso il nuovo kernel:

```bash
sudo reboot
```

### Se l'aggiornamento si ferma su una dipendenza ALSA

Senza il primo comando, sull'immagine di fabbrica l'aggiornamento si ferma con (provato su due schede):

```
alsa-ucm-conf : Depends: libasound2t64 (>= 1.2.15)
```

L'immagine prende i profili audio, il kernel, il firmware e mesa da `trixie-backports`, ma non la libreria ALSA che serve ai nuovi profili audio. Installa anche la libreria da backports, poi ripeti l'aggiornamento (la prima parte, già fatta, viene saltata):

```bash
sudo apt-get install -y -t trixie-backports libasound2t64 libasound2-data libatopology2t64 alsa-ucm-conf
arduino-app-cli system update
```

`scripts/install.sh` applica la stessa correzione, quindi sulle schede che installerai in seguito se ne occupa lui.

## 9. Controllare lo spazio libero

Sulla scheda usata per il progetto la partizione di sistema aveva circa 2 GB liberi su 9,8 GB, mentre `/home/arduino` è una partizione separata con circa 15 GB liberi. DomotiQ vive in `/home/arduino/domotiq`, quindi quella che conta è la partizione home:

```bash
df -h /home/arduino
```

Una prima installazione ha bisogno di circa 2,3 GB lì; l'installer lo controlla prima di cominciare.

## Prima di lasciare la casa ad altri

La password `domotiq2026` è scritta in questa guida, quindi chiunque la legga la conosce. Prima che altre persone possano collegarsi alla rete della casa:

- segui [Prima che la casa lasci il laboratorio](02-installazione.md#prima-che-la-casa-lasci-il-laboratorio): togli la rete del laboratorio e la cronologia dei comandi, e fai entrare SSH solo con la chiave se la casa resta a te, oppure togli le tue chiavi se la consegni;
- se vuoi, scegli un'altra password per `arduino` con `passwd`;
- se durante lo sviluppo hai dato all'utente `arduino` un `sudo` senza password, rimetti la password a `sudo` (la piccola regola installata da DomotiQ, che permette solo di riavviare i suoi servizi, riavviare o spegnere la scheda e cambiare l'hotspot, può restare).

Avanti: [installare il software](02-installazione.md).
