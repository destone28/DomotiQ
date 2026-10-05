<!-- SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Accelerare il modello linguistico sul processore della UNO Q

Questo documento descrive le istruzioni scritte apposta perché il modello linguistico della casa (Qwen2.5-0.5B-Instruct su llama.cpp) giri più veloce sul processore della Arduino UNO Q, e misura i risultati. Le istruzioni sono una patch di llama.cpp, `scripts/llama/arm-nodot.patch`, che `scripts/install.sh` applica alla versione di llama.cpp provata prima di compilarla.

**In breve.** Su casa1, con la casa accesa:
- **Richieste della casa al modello:** mediana da 3,41 a 2,18 secondi (1,56 volte più veloci). Ogni parola letta passa da 223 a 146 ms, ogni parola scritta da 295 a 188 ms. Il risultato viene dalle istruzioni nuove insieme alla flash attention spenta.
- **Lettura delle istruzioni dei comandi** (1556 parole, la prima volta che il server parte): da 196,7 a 112,6 secondi con le istruzioni nuove.
- **Moltiplicazioni di matrici del modello:** da 1,07 a 2,01 volte più veloci, con risultati uguali entro gli arrotondamenti.
- **Il modello intero** (llama-bench, libreria originale e nuova alternate): lettura 1,65 volte più veloce senza contesto e 1,34 volte con 1400 parole di contesto, scrittura con il contesto 1,20 volte. Senza contesto la scrittura dipende soprattutto dalla memoria, e con la casa accesa la differenza resta sotto il rumore della misura.

## Il processore

La UNO Q monta un Qualcomm QRB2210 con quattro core Cortex-A53 a 2,0 GHz (in `/proc/cpuinfo` *CPU part 0x801*, Kryo-V2). Sono core ARMv8.0-A con le istruzioni vettoriali NEON, ma:

- **senza il prodotto scalare a 8 bit** (SDOT/UDOT, `asimddp`): l'istruzione con cui llama.cpp somma 16 prodotti di numeri a 8 bit in un colpo solo;
- **senza la moltiplicazione di matrici a 8 bit** (I8MM) e **senza l'aritmetica a 16 bit in virgola mobile** (FP16);
- con un'unità vettoriale larga 64 bit: un'operazione NEON su 128 bit occupa due cicli;
- in ordine, con due istruzioni per ciclo al massimo: le catene di operazioni che dipendono l'una dall'altra lo rallentano più di un core moderno.

Le flag che il kernel Linux riporta sono `fp asimd evtstrm aes pmull sha1 sha2 crc32 cpuid`.

## Il modello

Il file si chiama `qwen2.5-0.5b-instruct-q4_k_m.gguf`, ma i formati "K" (Q4_K, Q6_K) richiedono righe lunghe un multiplo di 256 e la dimensione interna di Qwen2.5-0.5B è 896. Per questo quasi tutte le matrici sono in Q5_0:

| Formato | Matrici | Pesi | Parte del calcolo per parola |
|---|---|---|---|
| Q5_0 | ffn_gate, ffn_up, attn_q, attn_k, attn_output, metà di attn_v (e l'embedding, che però non si moltiplica) | 252 milioni nei prodotti | 70% in lettura, 51% in scrittura |
| Q4_K | ffn_down di 12 strati | 52 milioni | 15% in lettura, 11% in scrittura |
| Q6_K | ffn_down degli altri 12 | 52 milioni | 15% in lettura, 11% in scrittura |
| Q8_0 | output (la matrice finale, 151936 × 896) e metà di attn_v | 137 milioni | 28% in scrittura |

In lettura (il modello legge la richiesta) la matrice finale si usa solo per l'ultima parola; in scrittura (genera la risposta) serve a ogni parola.

## Cosa faceva llama.cpp su questo processore

- **Nessun formato riordinato.** llama.cpp ha versioni che riordinano i pesi a blocchi di 4 o 8 righe (*repack*), ma per ARM le abilita solo con SDOT o I8MM.
- **Il prodotto scalare emulato.** Senza SDOT ogni prodotto di 16 byte diventa due moltiplicazioni che allargano a 16 bit, due somme a coppie che allargano a 32 bit e una somma: 6 istruzioni, e i risultati di ogni sotto-blocco ridotti a un numero singolo.
- **Il quinto bit di Q5_0 attraverso la memoria.** Per ogni blocco di 32 pesi quattro valori di una tabella venivano scritti in memoria e riletti come vettore.
- **Una riga per una colonna alla volta.** Ogni blocco di pesi veniva spacchettato di nuovo per ogni parola della richiesta.

## Le istruzioni scritte

La patch aggiunge `ggml/src/ggml-cpu/arch/arm/quants-nodot.h` e modifica tre file di llama.cpp. Le nuove funzioni si attivano solo su processori ARM con NEON e senza SDOT, SVE e I8MM (la macro `GGML_NODOT_KERNELS`); sugli altri processori llama.cpp resta com'era.

1. **Prodotti sommati a 16 bit.** I prodotti di coppie di numeri a 8 bit si accumulano su 16 bit (SMULL, SMLAL) finché non possono traboccare, e si allargano a 32 bit una volta sola (SADDLP, SADALP). Per Q5_0 i pesi stanno tra -16 e 15, quindi ogni corsia a 16 bit tiene quattro prodotti (4 × 16 × 127 < 32767); per Q8_0 due.
2. **Il quinto bit di Q5_0 dalla tabella direttamente nei registri.** Gli otto byte della tabella si caricano con letture vettoriali da 64 bit, senza scrivere e rileggere. Una prima versione ricavava il bit con operazioni vettoriali (CMTST, BIC) ed era più lenta: su questo core ogni operazione a 128 bit costa due cicli, mentre le letture procedono in parallelo.
3. **Scale applicate alle somme parziali.** In Q4_K e Q6_K i fattori di scala dei sotto-blocchi moltiplicano le somme a 16 bit (SMLAL per elemento) e un super-blocco di 256 pesi si riduce una volta sola, invece di 8 (Q4_K) o 16 (Q6_K).
4. **Due righe per due colonne.** Quando il modello legge più parole insieme, ogni blocco di pesi spacchettato serve a due parole e ogni parola a due righe (Q5_0, Q4_K, Q6_K). llama.cpp usa questa forma solo con un numero pari di parole e di righe; la patch tratta le estremità una alla volta, così una richiesta di 17 parole non rinuncia alla forma doppia per tutto il prodotto.
5. **Due blocchi per giro e moltiplicazioni-somme fuse** (FMLA): due catene indipendenti per un core che esegue in ordine, un'istruzione invece di due per accumulare in virgola mobile.

## Verifica

- **Contro un riferimento esatto.** `scripts/llama/vdtest.c` confronta ogni prodotto scalare con lo stesso prodotto calcolato in doppia precisione sui valori dequantizzati, su righe casuali con valori anomali, una riga per una colonna e due per due. L'errore relativo massimo resta sotto 1 milionesimo, come con il codice originale (solo arrotondamenti).
- **Le moltiplicazioni di matrici del modello.** `scripts/llama/mmbench.c` esegue le moltiplicazioni con le forme e i formati di Qwen2.5-0.5B attraverso il percorso di llama.cpp e salva i risultati. Tra la versione originale e quella nuova la differenza massima è di 3 decimilionesimi del valore più grande; per Q4_K e Q6_K con una parola i risultati sono identici.
- **Le risposte della casa.** Le frasi vere mandate al server del modello danno le stesse risposte quando hanno un senso; le differenze su tre frasi senza senso sono spiegate nella sezione *Le richieste della casa*.

## Misure

### Le moltiplicazioni di matrici

`bench.py` con `mmbench.c`, 3 thread, il migliore di 3 giri; prima e dopo alternati.

| Moltiplicazione (matrici del modello) | Parole | Prima | Dopo | Più veloce |
|---|---|---|---|---|
| Q5_0 4864 × 896 (ffn_gate, ffn_up) | 1 | 1,148 ms | 0,974 ms | 1,18 volte |
| | 17 | 17,12 ms | 10,30 ms | 1,66 volte |
| | 64 | 63,11 ms | 34,15 ms | 1,85 volte |
| Q5_0 896 × 896 (attn_q, attn_output) | 1 | 0,209 ms | 0,178 ms | 1,17 volte |
| | 17 | 3,244 ms | 1,827 ms | 1,78 volte |
| | 64 | 11,79 ms | 6,40 ms | 1,84 volte |
| Q5_0 128 × 896 (attn_k) | 1 | 0,038 ms | 0,030 ms | 1,27 volte |
| | 17 | 0,495 ms | 0,261 ms | 1,90 volte |
| | 64 | 1,795 ms | 0,891 ms | 2,01 volte |
| Q4_K 896 × 4864 (ffn_down) | 1 | 0,884 ms | 0,691 ms | 1,28 volte |
| | 64 | 51,94 ms | 27,98 ms | 1,86 volte |
| Q6_K 896 × 4864 (ffn_down) | 1 | 1,465 ms | 1,050 ms | 1,40 volte |
| | 64 | 74,81 ms | 56,13 ms | 1,33 volte |
| Q8_0 128 × 896 (attn_v) | 1 | 0,030 ms | 0,027 ms | 1,11 volte |
| | 64 | 1,704 ms | 1,386 ms | 1,23 volte |
| Q8_0 151936 × 896 (output) | 1 | 31,17 ms | 29,13 ms | 1,07 volte |

Con una parola sola il guadagno è minore: i pesi vanno letti dalla memoria a ogni parola, e la matrice finale (145 MB in Q8_0) è limitata dalla memoria più che dal calcolo. Con più parole ogni peso letto serve più volte e conta il calcolo.

Le versioni intermedie, provate e scartate o corrette:
- il quinto bit di Q5_0 ricavato con operazioni vettoriali: con una parola era più lento dell'originale (0,94-0,99 volte);
- le due righe per due colonne usate solo con un numero pari di parole, come faceva llama.cpp: con 17 parole Q5_0 non guadagnava niente.

### Il modello intero

`ab_bench.py`: lo stesso llama-bench con la libreria originale e con quella nuova (la libreria si sceglie con `LD_LIBRARY_PATH`), alternate prova per prova, 3 thread, mediana di 3 giri. Con il contesto la flash attention è spenta, come nel servizio.

| Prova | Originale | Nuova | Più veloce |
|---|---|---|---|
| Lettura di 16 parole, senza contesto | 9,36 parole/s | 15,47 parole/s | 1,65 volte |
| Lettura di 16 parole, 1400 parole di contesto | 6,06 parole/s | 8,14 parole/s | 1,34 volte |
| Scrittura di 8 parole, 1400 parole di contesto | 3,39 parole/s | 4,06 parole/s | 1,20 volte |
| Scrittura di 8 parole, senza contesto | 5,38 parole/s | 5,32 parole/s | sotto il rumore della misura |

- **Lettura e scrittura con il contesto:** in tutti e tre i giri la libreria nuova è stata la più veloce.
- **Scrittura senza contesto:** per ogni parola scritta il processore legge dalla memoria quasi tutto il modello (il file è di 491 MB, la sola matrice finale di 145 MB), e conta soprattutto la memoria. Con la casa accesa la sintesi vocale e la visione occupano i core a tratti: una delle tre misure della libreria nuova è scesa a 1,32 parole/s. Anche una seconda prova più lunga (16 parole, 5 ripetizioni, 4 giri) ha dato valori tra 1,99 e 5,92 parole/s: con la casa accesa questa differenza non si riesce a misurare.

### L'attenzione sul contesto

Le istruzioni dei comandi della casa occupano circa 1550 parole, già lette e tenute in memoria. Ogni richiesta nuova deve confrontarsi con tutte (l'attenzione), e con questo contesto llama.cpp legge e scrive molto più piano che senza. llama-bench, libreria originale, 3 thread:

| | Senza contesto | Con 1400 parole di contesto |
|---|---|---|
| Lettura (16 parole) | 10,57 parole/s | 5,71 parole/s |
| Scrittura (4 parole) | 6,17 parole/s | 3,74 parole/s |

Con 1400 parole di contesto:

| Attenzione | Lettura | Scrittura |
|---|---|---|
| flash attention (l'impostazione automatica, in uso) | 5,77 parole/s | 3,70 parole/s |
| contesto in Q8_0 | 6,61 parole/s | 4,28 parole/s |
| flash attention spenta | 7,78 parole/s | 4,56 parole/s |

Senza flash attention llama.cpp calcola l'attenzione come moltiplicazioni di matrici, che su questo processore vanno meglio. Il servizio `domotiq-llm` ora parte con `-fa off`. Con la flash attention spenta la memoria del contesto è disposta in un altro modo: i file in cui la casa salva le istruzioni già lette hanno quindi un nome nuovo (`SLOTS_LAYOUT` in `voice/llm.py`), e la prima volta le istruzioni si rileggono.

### Le richieste della casa

`e2e.py`: un server del modello avviato a parte (`-np 1 -c 4096`, 3 thread) legge le istruzioni dei comandi, poi riceve le dieci frasi che casa1 aveva davvero mandato al modello (dal registro: "la cucina è vuota", "always in the living room", "what is rose", "che meteo ci sarà tradate domani"...). I tempi vengono dal server stesso.

| Configurazione | Istruzioni (1556 parole) | Richiesta: mediana | Media | Per parola letta | Per parola scritta |
|---|---|---|---|---|---|
| A. Come prima | 196,7 s | 3,41 s | 3,46 s | 223 ms | 295 ms |
| B. Istruzioni nuove | 112,6 s | 2,99 s | 3,07 s | 188 ms | 275 ms |
| C. Istruzioni nuove, flash attention spenta (in uso) | 154,7 s | 2,18 s | 2,28 s | 146 ms | 188 ms |
| D. Come C, contesto in virgola mobile a 32 bit | 168,7 s | 2,68 s | 2,74 s | 184 ms | 206 ms |

- **C contro A:** richieste 1,56 volte più veloci in mediana, lettura 1,53 volte, scrittura 1,57 volte.
- **Le istruzioni lunghe** si leggono più in fretta con la flash attention (B): servono solo alla prima accensione, poi la casa le ripone da file in pochi secondi. Per questo la scelta è C.
- **Il contesto a 32 bit** (D) muove il doppio dei dati e va più piano.
- **Le risposte.** Sulle frasi con un senso le risposte sono le stesse in tutte le configurazioni ("la cucina è vuota" → *count living*, "what is rose" → *who_in living*, "che meteo ci sarà tradate domani" → *other*...). Su tre frasi senza senso, storpiate dal riconoscimento ("giusto si no si", "blu giusto", "enzo giorno"), la risposta cambia tra *other* e un comando. Cambia però anche tra due esecuzioni della libreria originale (il server in uso contro quello avviato a parte): il modello è al limite tra due risposte, e basta un diverso ordine delle somme in virgola mobile. La casa poi esegue un'azione proposta dal modello solo se ne è abbastanza sicuro.

## Come ripetere le misure

Gli strumenti sono in `scripts/llama/`:

- `vdtest.c`: la verifica dei prodotti scalari;
- `mmbench.c`: una moltiplicazione con tempo e risultato salvato (`mmbench q5_0 4864 896 64 3 4 out.bin`: formato, righe, lunghezza della riga, parole, thread, ripetizioni);
- `bench.py`: tutte le moltiplicazioni del modello con due librerie a confronto, alternate;
- `ab_bench.py`: il modello intero con llama-bench, la libreria originale e quella nuova alternate;
- `e2e.py`: un server del modello avviato a parte, con le istruzioni dei comandi della casa e le frasi vere.

Si compilano sulla scheda contro la libreria di llama.cpp:

```bash
L=~/domotiq/llama.cpp
gcc -O2 -o mmbench scripts/llama/mmbench.c -I$L/ggml/include -L$L/build/bin -lggml -lggml-base -lggml-cpu -lm -Wl,-rpath,$L/build/bin
gcc -O2 -o vdtest  scripts/llama/vdtest.c  -I$L/ggml/include -L$L/build/bin -lggml -lggml-base -lggml-cpu -lm -Wl,-rpath,$L/build/bin
```

Per i confronti servono due copie di llama.cpp alla stessa versione, compilate allo stesso modo, una senza e una con la patch: `bench.py` e `ab_bench.py` ricevono gli strumenti o le cartelle `build/bin` di entrambe (`python3 scripts/llama/ab_bench.py <llama-bench> <build/bin originale> <build/bin nuova>`).

Le misure di questo documento sono state fatte su casa1 con la casa accesa e a riposo (visione, voce e parola di attivazione attive), con 3 thread come il servizio `domotiq-llm`; per i prodotti è riportato il migliore di 3 giri, per il modello intero la mediana di 3 giri, sempre alternando le due librerie.
