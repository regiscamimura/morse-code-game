#!/usr/bin/env python3
"""MORSE CODE - Station Seven, 1936. A Morse code story for the terminal.

TAP space = dit (•)    HOLD space = dah (━)

With access to /dev/input (the `input` group) the space bar's real press and
release are read, and a press of --dah-time or longer is a dah. Without it,
terminals send no key-release events, so a hold is recognised from the
keyboard's autorepeat burst; tune --repeat-delay / --repeat-interval then.
"""
import argparse
import fcntl
import itertools
import json
import math
import os
import random
import select
import struct
import subprocess
import sys
import termios
import threading
import time
import tty
import unicodedata

MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.', 'H': '....',
    'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 'P': '.--.',
    'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
}
DECODE = {v: k for k, v in MORSE.items()}
DOT, DAH = '•', '━'

# Koch-style unlock order: chapter N adds LEVELS[N-1].
LEVELS = ['ETAN', 'IM', 'SO', 'RK', 'DU', 'GW', 'HV', 'FL', 'BC', 'PJ', 'XY', 'ZQ']

WORDS_EN = """
TNT NET TEN TAN NEAT TENT ANTE ANTENNA AIM MINE MINT TIME MAN MEN TEAM ITEM MAIN INMATE MEANT
SOS STONE SAINT MOST MOAT ATOMS MOTION NATION STATION MANSION AMMO SEA MASON MOON NOON
ARMS STORM SMOKE STRIKE TRAITOR MARKS TRAIN MARINE ARMOR RANK MARK STAR TRAMS ROSE
RAID DUST UNDER ROUND SOUND MURDER TORNADO DIAMOND DOOR DUKE DRUM RADIO ROUTE
WAR GUN GUNS WORD SWORD TOWER WAGON GRENADE WARDEN WIDOW MAGNET WIRE WIRES WATER WINTER AGENT
HUNT HUNTER SHADOW HERO SHOT THUNDER WARHEAD INVADE INVADER HAVEN ANTHEM NORTH SOUTH
FLAG FIRE FLARE FUSE FLEET SHELL NAVAL RIFLE FLAME FUEL SOLDIER SIGNAL ADMIRAL TELEGRAM LIGHT
BOMB BUNKER CODE SECRET CANNON ATTACK BOMBER ABORT COMBAT CASTLE BRIDGE BULLET DECODE BEACON
DOCK HARBOUR CABLE COURIER TORPEDO PATROL PIRATE PILOT SNIPER ESCAPE PANIC HIJACK CIPHER
PERIL TRAP CAPTAIN PLANS PLANE OPERATOR PASSPORT SPY ENEMY ARMY NAVY EXPLODE MYSTERY
TYPHOON PAYLOAD JETTY EXPRESS ZERO BLITZ QUAKE SQUAD QUEST FREEZE QUAY AZIMUTH QUEEN ZEPPELIN
""".split()

# 1930s poster palette: navy night, brass, cream, teal for receiving,
# oxblood for sending and danger, signal green for success, warm lamp yellow.
INK, NIGHT, EARTH, SEA, FOG = (10, 12, 22), (16, 26, 56), (44, 34, 26), (14, 44, 64), (54, 62, 74)
FAINT, DIM, AMBER = (62, 70, 88), (130, 138, 152), (218, 166, 60)
PAPER, BRIGHT, ALERT = (234, 224, 198), (255, 246, 220), (210, 66, 52)
TEAL, GO, LAMP, FLAME = (72, 178, 172), (118, 192, 96), (252, 208, 88), (236, 124, 40)
EMBER, BAND, SEND_BAND, LISTEN_BAND = (72, 20, 14), (22, 32, 60), (110, 32, 30), (18, 72, 78)
PAL = {'K': INK, 'D': FAINT, 'S': DIM, 'A': AMBER, 'O': FLAME, 'W': PAPER, 'Y': LAMP,
       'R': ALERT, 'T': TEAL}

SPRITES = {
    'spark': ['YO', 'OY'],
    'bomb': ['.......OY.', '......O...', '.....SS...', '...DDDDDD.',
             '..DDWDDDDD', '..DWDDDDDD', '..DDDDDDDD', '...DDDDDD.'],
    'city': ['......S.......', '.....SSS......', '..TT.SYS..AA..', '..TT.SSS..AA..',
             '.SYTTSYS.SAYS.', '.SSTTSSS.SAAS.', 'SSYSSSYSSSSYSS', 'SSSSSSSSSSSSSS'],
    'station': ['......R.......', '......S.......', '.....S.S......', '....S.S.S.....',
                '..RRRRRRRRRR..', '.AAAAAAAAAAAA.', '.AYYAAAAAAYYA.', '.AAAAAAAAAAAA.'],
    'airship': ['R...SSSSSSSSSSSS....', 'RR.SWWWWWWWWWWWWSS..', 'RRSWWWWWWWWWWWWWWWS.',
                'RR.SWWWWWWWWWWWWSS..', 'R...SSSSSSSSSSSS....', '........DYD.........'],
    'biplane': ['..AAAAAAAAA...', '....D...D.....', 'R..RRRRRRRRRW.',
                'RRRRRRRRRRRRW.', '..AAAAAAAAA...', '....D...D.....'],
    'train': ['.............W..', '..TTTT.......DD.', '..TYYT.......DD.',
              'TTTTTTTTTTTTTTTT', 'SSSSSSSSSSSSSSSR', '.DD..DD..DD..DD.'],
    'liner': ['.....K...K........', '.....R...R........', '...WWWWWWWWWWW....',
              'SSSSYSSYSSYSSYSSSS', '.SSSSSSSSSSSSSSSS.', '..SSSSSSSSSSSSSS..'],
    'submarine': ['......SS........', '.....SSSS.......', '..DDDDDDDDDDDD..', '.DDDDDDDDDDDDDD.'],
    'lighthouse': ['..YYYY..', '..DSSD..', '...RR...', '...WW...',
                   '...RR...', '..WWWW..', '..RRRR..', '.SSSSSS.'],
    'car': ['....TTTT....', '..TTTTTTTT..', '.TTTTTTTTTTY', 'TTTTTTTTTTTT', '.DD......DD.'],
}
FLYERS = {'airship', 'biplane'}

# scene: (mover, target, sky, ground). The mover creeping toward the target is the timer.
SCENES = {
    'wireless': ('airship', 'station', NIGHT, EARTH),
    'rail': ('train', 'city', NIGHT, EARTH),
    'harbour': ('submarine', 'liner', NIGHT, SEA),
    'fog': ('liner', 'lighthouse', FOG, SEA),
    'bomb': ('spark', 'bomb', NIGHT, EARTH),
    'road': ('car', 'station', NIGHT, EARTH),
    'air': ('biplane', 'station', NIGHT, EARTH),
}


def beat(mode, title, brief, task, win, lose, scene, echo=False):
    """One mission. echo=True reuses the word decoded in the previous mission."""
    return dict(mode=mode, title=title, brief=brief, task=task, win=win, lose=lose, scene=scene, echo=echo)


CHAPTERS_EN = [
    dict(title='STATION SEVEN', intro=[
        'NOVEMBER 1936. A WIRELESS STATION ON A GREY STRETCH OF COAST.',
        'YOUR POSTING: NIGHT OPERATOR. YOUR DUTY: LISTEN.',
        'COMMANDER HALE OF NAVAL INTELLIGENCE CALLS IT A QUIET POST.'], beats=[
        beat('encode', 'FIRST WATCH', [
            'MIDNIGHT. THE VALVES WARM. THE AERIAL HUMS IN THE WIND.',
            'THE ADMIRALTY EXPECTS A SIGNAL CHECK BEFORE THE HOUR.'],
            'SEND THE CHECK WORD.',
            "HALE: 'RECEIVED, SPARKS. KEEP YOUR EARS OPEN.'",
            'THE HOUR PASSES. YOUR SILENCE IS NOTED IN THE LOG.', 'wireless'),
        beat('decode', 'AN UNLISTED BAND', [
            '0300. A SIGNAL ON A FREQUENCY NO ONE IS ASSIGNED.',
            'IT REPEATS. SLOW AND DELIBERATE.'],
            'DECODE IT BEFORE IT FADES.',
            'ONE WORD: {word}. THEN NOTHING.',
            'THE SIGNAL SINKS INTO THE STATIC.', 'wireless'),
        beat('encode', 'REPORT', [
            'HALE MUST HEAR OF THIS TONIGHT.',
            'REPEAT THE WORD EXACTLY AS YOU RECEIVED IT.'],
            'SEND THE WORD TO THE ADMIRALTY.',
            "A LONG PAUSE. HALE: 'SAY NOTHING TO ANYONE.'",
            'THE LINE GOES DEAD.', 'wireless', echo=True),
    ]),
    dict(title='NIGHTJAR', intro=[
        'HALE EXPLAINS IN A SEALED LETTER, DELIVERED BY HAND.',
        'NIGHTJAR: A RING THAT SELLS NAVAL SECRETS TO THE HIGHEST BIDDER.',
        'THEY TALK AT NIGHT, AND THEY TALK IN MORSE.'], beats=[
        beat('decode', 'THE MEETING', [
            'NIGHTJAR TRAFFIC ON THE NIGHT BAND.',
            'A PLACE IS BEING NAMED.'],
            'DECODE THE MEETING PLACE.',
            'THEY MEET AT {word}. HALE SENDS MEN TO WATCH.',
            'THE MESSAGE ENDS. THE MEETING GOES UNOBSERVED.', 'wireless'),
        beat('encode', 'THE NIGHT TRAIN', [
            'A COURIER WITH ADMIRALTY PAPERS IS ON THE NIGHT TRAIN.',
            'NIGHTJAR MEN BOARDED AT THE LAST STOP.'],
            'WIRE THE NEXT STATION TO HOLD THE TRAIN.',
            'THE TRAIN IS HELD. THE COURIER IS SAFE.',
            'THE TRAIN RUNS ON. THE PAPERS ARE GONE BY MORNING.', 'rail'),
        beat('decode', 'A NAME', [
            'THE COURIER HEARD THE MEN TAP A NAME ON THE CARRIAGE WALL.',
            'THEY THOUGHT NO ONE ABOARD COULD READ IT.'],
            'DECODE THE NAME.',
            'THE NAME IS {word}. HALE GOES VERY QUIET.',
            'THE COURIER CANNOT RECALL IT.', 'rail'),
    ]),
    dict(title='THE LAMP', intro=[
        'ONLY THREE PEOPLE KNEW THE COURIER WAS ON THAT TRAIN.',
        'HALE. THE COURIER. AND YOU.',
        'TONIGHT, A LAMP IS SIGNALLING FROM THE HEADLAND.'], beats=[
        beat('decode', 'THE HEADLAND', [
            'A LIGHT ON THE CLIFFS. ON. OFF. ON.',
            'SOMEONE IS SIGNALLING A VESSEL OFFSHORE.'],
            'READ THE LAMP.',
            'THE LAMP SPELLS {word}. THEY KNOW THE STATION IS LISTENING.',
            'THE LAMP GOES OUT.', 'harbour'),
        beat('encode', 'THE HARBOUR MASTER', [
            'A VESSEL IS COMING IN FOR WHOEVER HOLDS THE LAMP.',
            'THE HARBOUR CAN BE CLOSED, IF THE MASTER IS WARNED IN TIME.'],
            'SEND THE CLOSURE ORDER.',
            'THE BOOM IS DRAWN ACROSS THE HARBOUR. THE VESSEL TURNS AWAY.',
            'THE VESSEL COMES AND GOES UNSEEN.', 'harbour'),
        beat('decode', 'THE NOTE', [
            'MORNING. A FOLDED NOTE UNDER THE STATION DOOR.',
            'NOT WRITTEN. PRICKED IN DOTS AND DASHES.'],
            'DECODE THE NOTE BEFORE THE RAIN RUINS IT.',
            "THE NOTE READS {word}. IT IS SIGNED 'W'.",
            'THE INK RUNS. THE NOTE IS LOST.', 'wireless'),
    ]),
    dict(title='THE GALE', intro=[
        'THE WORST GALE IN TWENTY YEARS.',
        'THE MAINS FAIL AT MIDNIGHT. THE STATION RUNS ON BATTERIES.',
        'EVERY MINUTE OF POWER COUNTS.'], beats=[
        beat('decode', 'DISTRESS', [
            'A LINER IS LOST IN FOG OFF THE POINT. HER SIGNAL IS WEAK.',
            'HER OPERATOR IS SENDING WHAT CAN BE SEEN FROM THE BRIDGE.'],
            'DECODE THE LANDMARK.',
            'THEY CAN SEE {word}. YOU KNOW EXACTLY WHERE THAT IS.',
            'THE SIGNAL DIES IN THE GALE.', 'fog'),
        beat('encode', 'THE BEARING', [
            'THE LINER IS STEAMING TOWARD THE ROCKS.',
            'ONE CORRECTION, BEFORE THE BATTERIES GIVE OUT.'],
            'SEND THE BEARING.',
            'THE LINER TURNS. HER LIGHTS PASS SAFELY BY THE POINT.',
            'THE BATTERIES FAIL MID-WORD.', 'fog'),
        beat('encode', 'THE PARCEL', [
            'A PARCEL WASHED UP WITH THE STORM. IT IS TICKING.',
            'A NIGHTJAR DEVICE, WITH A TELEGRAPH KEY FOR A LOCK.'],
            'TAP THE CODE THAT STOPS IT.',
            'THE TICKING STOPS.',
            'THE BEACH IS LIT FOR A MOMENT. THEN DARK.', 'bomb'),
    ]),
    dict(title='WREN', intro=[
        "THE NOTE WAS SIGNED 'W'.",
        'HALE ADMITS IT AT LAST: WREN IS OUR AGENT INSIDE NIGHTJAR.',
        'WREN WILL SPEAK TO NO ONE BUT YOU.'], beats=[
        beat('encode', 'RECOGNITION', [
            'WREN WILL ONLY ANSWER THE CORRECT RECOGNITION WORD.',
            'A NIGHTJAR PATROL CAR IS ALREADY ON THE COAST ROAD.'],
            'SEND THE RECOGNITION WORD.',
            'A PAUSE. THEN TWO DOTS. WREN IS LISTENING.',
            'NO REPLY. WREN STAYS SILENT.', 'road'),
        beat('decode', 'WHAT WAS TAKEN', [
            'WREN SENDS QUICKLY, HAND UNSTEADY.',
            'NIGHTJAR HAS TAKEN SOMETHING FROM A NAVAL ARSENAL.'],
            'DECODE WHAT WAS TAKEN.',
            "WREN: '{word}. AND THE NEW CIPHER MACHINE.'",
            'WREN STOPS MID-SENTENCE.', 'wireless'),
        beat('decode', 'THE ROUTE', [
            'THE MACHINE IS TO BE SOLD ABROAD.',
            'WREN KNOWS THE ROUTE.'],
            'DECODE THE ROUTE.',
            'IT LEAVES BY {word}. THE NET TIGHTENS.',
            'STATIC. WREN IS GONE FOR THE NIGHT.', 'wireless'),
    ]),
    dict(title='THE AIRSHIP', intro=[
        'THE CIPHER MACHINE IS ABOARD AN AIRSHIP BOUND FOR THE CONTINENT.',
        'NO PASSENGERS LISTED. NO CARGO DECLARED.',
        'IT CROSSES THE COAST TONIGHT.'], beats=[
        beat('decode', 'NAVIGATION', [
            'THE AIRSHIP CHECKS IN WITH A GROUND STATION.',
            'IT IS NAMING ITS NEXT WAYPOINT.'],
            'DECODE THE WAYPOINT.',
            'WAYPOINT {word}. NOW YOU KNOW ITS COURSE.',
            'THE AIRSHIP PASSES OVER IN SILENCE.', 'wireless'),
        beat('encode', 'FALSE STATION', [
            'IF THE CAPTAIN HEARS THE WRONG CALL SIGN, THE AIRSHIP WILL TURN.',
            'PRETEND TO BE THEIR GROUND STATION.'],
            'SEND THE FALSE CALL SIGN.',
            'THE AIRSHIP ALTERS COURSE, INLAND, TOWARD OUR AIRFIELD.',
            'THE CAPTAIN IS NOT DECEIVED.', 'wireless'),
        beat('encode', 'INTERCEPT', [
            'TWO BIPLANES ARE READY AT THE AIRFIELD.',
            'THEY WILL NOT TAKE OFF WITHOUT ORDERS.'],
            'SEND THE ORDER TO INTERCEPT.',
            'THE AIRSHIP IS BROUGHT DOWN INTACT. THE HOLD IS EMPTY.',
            'THE AIRSHIP VANISHES INTO CLOUD.', 'wireless'),
    ]),
    dict(title='BENEATH', intro=[
        'THE AIRSHIP WAS A DECOY.',
        'THE MACHINE WENT TO SEA INSTEAD,',
        'ABOARD A SUBMARINE THAT FLIES NO FLAG.'], beats=[
        beat('decode', 'HYDROPHONE', [
            'THE SUBMARINE SIGNALS ITS TENDER BY TAPPING ON THE HULL.',
            'THE HYDROPHONE STATION PATCHES THE TAPPING THROUGH TO YOU.'],
            'DECODE THE TAPPING.',
            'THE SUBMARINE SENDS {word}. IT IS STALKING THE MAIL STEAMER.',
            'THE TAPPING STOPS. THE SUBMARINE DIVES.', 'harbour'),
        beat('encode', 'WARN THE STEAMER', [
            'THE MAIL STEAMER DOES NOT KNOW IT IS BEING FOLLOWED.',
            'THE SUBMARINE IS CLOSING.'],
            'SEND THE WARNING.',
            'THE STEAMER CHANGES COURSE AND RUNS FOR PORT.',
            'THE STEAMER NEVER HEARD YOU.', 'harbour'),
        beat('encode', 'SURFACE', [
            'A DESTROYER HAS THE SUBMARINE BOXED IN.',
            'IT WANTS THE MACHINE BACK, NOT A WRECK.'],
            'SEND THE ORDER TO SURFACE.',
            'THE SUBMARINE SURFACES. THE CREW SURRENDERS. NO MACHINE ABOARD.',
            'THE SUBMARINE SLIPS AWAY IN THE DARK.', 'harbour'),
    ]),
    dict(title='BURNED', intro=[
        'WREN SENDS ONE LINE IN DAYLIGHT, AGAINST EVERY RULE:',
        "'THEY KNOW.'",
        'THEN NOTHING.'], beats=[
        beat('decode', 'SAFE HOUSE', [
            'HOURS LATER. A FAINT SIGNAL FROM INLAND.',
            'WREN IS HIDING, AND SENDING THE ADDRESS.'],
            'DECODE THE HIDING PLACE.',
            'WREN IS AT {word}. HOLD ON, WREN.',
            'THE SIGNAL CUTS OUT.', 'wireless'),
        beat('encode', 'EXTRACTION', [
            'A NIGHTJAR CAR IS ALREADY ON THE ROAD TO THE SAFE HOUSE.',
            'OUR DRIVER WAITS ONLY FOR THE WORD.'],
            'SEND THE WORD.',
            'HEADLAMPS IN THE LANE. WREN IS AWAY.',
            'THE NIGHTJAR CAR ARRIVES FIRST.', 'road'),
        beat('decode', "WREN'S WARNING", [
            'FROM THE BACK OF THE CAR, WREN TAPS ONE WORD ON A PORTABLE SET.',
            'THE CODENAME OF WHOEVER RUNS NIGHTJAR.'],
            'DECODE THE CODENAME.',
            'NIGHTJAR IS RUN BY {word}. WREN SAYS IT IS SOMEONE INSIDE.',
            'THE CAR DRIVES OUT OF RANGE.', 'road'),
    ]),
    dict(title='THE FIST', intro=[
        'EVERY OPERATOR HAS A FIST: A RHYTHM AS PERSONAL AS HANDWRITING.',
        'NIGHTJAR ALWAYS KNEW WHAT THE ADMIRALTY KNEW.',
        'YOU BEGIN TO LISTEN TO OLD RECORDINGS.'], beats=[
        beat('decode', 'THE CYLINDERS', [
            'WAX CYLINDERS OF ADMIRALTY TRAFFIC FROM LAST MONTH.',
            'BENEATH THE ROUTINE MESSAGES, A SECOND HAND IS SENDING.'],
            'DECODE THE HIDDEN SENDING.',
            'IT SAYS {word}. YOU KNOW THAT FIST. IT IS HALE.',
            'THE CYLINDER CRACKS.', 'wireless'),
        beat('encode', 'TRUST NO ONE', [
            'HALE CONTROLS THE ADMIRALTY LINES.',
            'ONLY WREN CAN BE TRUSTED NOW.'],
            'SEND WREN THE ALARM WORD.',
            "WREN ANSWERS: 'UNDERSTOOD. TRUST NO ONE.'",
            'THE MESSAGE GOES OUT ON AN OPEN BAND. HALE HEARS IT.', 'wireless'),
        beat('decode', 'HALE CALLS', [
            'THE ADMIRALTY LINE OPENS. HALE IS CALLING. VERY CALM.',
            'TOO CALM. A CODEWORD IS BURIED IN THE ROUTINE TRAFFIC.'],
            'DECODE THE BURIED CODEWORD.',
            'THE CODEWORD IS {word}. IT MEANS: SILENCE STATION SEVEN.',
            'HALE CLOSES THE LINE.', 'wireless'),
    ]),
    dict(title='ALONE', intro=[
        'THE ADMIRALTY NOW LISTS YOU AS ABSENT WITHOUT LEAVE.',
        'A NIGHTJAR AIRCRAFT IS COMING FOR THE STATION.',
        'THE AIRFIELD MAY STILL ANSWER AN HONEST OPERATOR.'], beats=[
        beat('encode', 'DISTRESS CALL', [
            'THE AIRCRAFT IS ALREADY OVER THE WATER.',
            'THE AIRFIELD IS YOUR ONLY CHANCE.'],
            'SEND THE DISTRESS CALL.',
            'TWO BIPLANES RISE TO MEET IT. THE INTRUDER TURNS BACK.',
            'NO ONE ANSWERS.', 'air'),
        beat('decode', 'THE PILOT', [
            'NIGHTJAR IS JAMMING THE BAND. ONE PILOT STILL GETS THROUGH.',
            'YOU MUST KNOW WHO IS UP THERE.'],
            "DECODE THE PILOT'S CALL SIGN.",
            'CALL SIGN {word}. A FRIEND. THE SKY IS HELD.',
            'THE JAMMING SWALLOWS EVERYTHING.', 'air'),
        beat('encode', 'THE BAIT', [
            'HALE BELIEVES YOU ARE FINISHED.',
            'SEND SOMETHING HALE WILL BELIEVE: A SURRENDER.'],
            'SEND THE SURRENDER WORD.',
            "HALE TAKES THE BAIT: 'COME TO THE STATION. ALONE.'",
            'HALE SUSPECTS THE TRAP.', 'wireless'),
    ]),
    dict(title='THE DEVICE', intro=[
        'HALE DID NOT COME ALONE.',
        'A DEVICE HAS BEEN LEFT BENEATH THE TRANSMITTER ROOM.',
        'ITS CLOCK IS ALREADY RUNNING.'], beats=[
        beat('decode', 'THE DIAGRAM', [
            'WREN HAS THE DIAGRAM.',
            'WREN SENDS THE FIRST STEP, SLOWLY.'],
            'DECODE THE FIRST WIRE.',
            'THE {word} WIRE IS CUT. YOUR HANDS ARE SHAKING.',
            'YOU MISS IT. THE CLOCK RUNS FASTER.', 'bomb'),
        beat('encode', 'THE KEY', [
            'THE DEVICE HAS ITS OWN TELEGRAPH KEY.',
            'IT WANTS A CODE, SENT CLEANLY.'],
            'SEND THE DISARM CODE.',
            'THE FIRST LOCK RELEASES. ONE REMAINS.',
            'THE CLOCK DOES NOT STOP.', 'bomb'),
        beat('encode', 'LAST LOCK', [
            'ONE LOCK LEFT. THE CLOCK IS COUNTING IN SECONDS.',
            'OUTSIDE, HALE IS WAITING TO HEAR IT GO.'],
            'SEND THE FINAL CODE.',
            'THE CLOCK STOPS. YOU REMEMBER TO BREATHE.',
            'STATION SEVEN IS GONE.', 'bomb'),
    ]),
    dict(title='LAST SIGNAL', intro=[
        'HALE IS RUNNING FOR THE HARBOUR.',
        'THE WORLD SHOULD KNOW WHAT HALE HAS DONE.',
        'ONE TRANSMITTER. ONE NIGHT. EVERY LETTER YOU KNOW.'], beats=[
        beat('decode', 'THE ESCAPE', [
            'HALE SIGNALS A WAITING VESSEL.',
            "HALE'S FIST IS UNSTEADY NOW."],
            'DECODE THE PLAN.',
            'HALE MEANS TO SAIL FOR {word}. NOT TONIGHT.',
            'THE VESSEL SLIPS ITS MOORINGS.', 'harbour'),
        beat('encode', 'THE BOOM', [
            'THE HARBOUR MASTER STILL TAKES ORDERS BY WIRE.',
            'THE BOOM CAN BE CLOSED ONE LAST TIME.'],
            'SEND THE CLOSURE ORDER.',
            'THE BOOM SWINGS SHUT. HALE IS TAKEN ON THE QUAY.',
            'THE VESSEL CLEARS THE HARBOUR.', 'harbour'),
        beat('encode', 'ALL STATIONS', [
            'EVERY STATION ON THE COAST IS LISTENING TONIGHT.',
            'TELL THEM.'],
            'SEND THE FINAL WORD.',
            'THE MESSAGE GOES OUT TO ALL STATIONS. NIGHTJAR IS FINISHED.',
            'THE TRANSMITTER FALTERS. SEND IT AGAIN.', 'wireless'),
    ]),
]
ENDING_EN = [
    'DAWN OVER THE COAST. THE GALE HAS PASSED.',
    'WREN SENDS ONE LAST SIGNAL:  DIT DIT DIT DAH DIT DAH.',
    'SK. END OF WORK.',
    'STATION SEVEN CLOSES DOWN.',
]
WIN_BANNERS_EN = ['RECEIVED', 'CONFIRMED', 'ACKNOWLEDGED']
LOSE_BANNERS_EN = ['TOO LATE', 'NO REPLY', 'SIGNAL LOST']

WORDS_PT = """
ANTA NATA ANTE TENTA ANTENA MINA MATE TIME MEIA META MENTE MANTA TINTA MITO
NOITE MONTE SANTO MASSA ESTANTE MISSA ASSASSINO TOSSE MOSTO SOS
MAR TREM TORRE TERRA ROTA ROSTO MORTE SERRA MESTRE ARMAS TIRO MARINA ARMA
RADIO DUNA MUNDO DESTINO ORDEM DOURADO UNIDADE DOMINO DEDO RUMO
GUERRA AGENTE GRANADA TIGRE GUARDA AGUA SEGREDO
NAVIO VENTO HAVANA HORA VIGIA VINHO HINO NEVE NOVE HOMEM
FAROL FOGO LUA FILME SINAL LINHA FLORESTA ALMIRANTE TELEGRAMA FUGA FERRO SELO
BOMBA CODIGO CIFRA BARCO CABO BALA CAIS CORREIO SECRETO ESCUDO CASCO CERCO
PILOTO PORTO PAPEL PERIGO JANELA PIRATA PATRULHA OPERADOR PASSAPORTE JORNAL HOJE
EIXO TAXI PEIXE XERIFE ROXO EXATO
ZERO ZEPELIM QUARTEL ZONA AZUL CRUZ VOZ PAZ QUILHA BUZINA ZARPAR AQUI
""".split()

CHAPTERS_PT = [
    dict(title='POSTO SETE', intro=[
        'NOVEMBRO DE 1936. UM POSTO DE ESCUTA NUM TRECHO CINZENTO DO LITORAL.',
        'SUA FUNÇÃO: RADIOTELEGRAFISTA DA NOITE. SEU DEVER: ESCUTAR.',
        'O COMANDANTE HALE, DA INTELIGÊNCIA NAVAL, DIZ QUE AQUI NADA ACONTECE.'], beats=[
        beat('encode', 'PRIMEIRO TURNO', [
            'MEIA-NOITE. AS VÁLVULAS ESQUENTAM. A ANTENA ZUNE AO VENTO.',
            'O ALMIRANTADO ESPERA UM TESTE DE SINAL ANTES DA HORA CHEIA.'],
            'ENVIE A PALAVRA DE TESTE.',
            "HALE: 'RECEBIDO, FAÍSCA. MANTENHA OS OUVIDOS ABERTOS.'",
            'A HORA PASSA. SEU SILÊNCIO FICA REGISTRADO NO LIVRO.', 'wireless'),
        beat('decode', 'UMA FAIXA SEM DONO', [
            'TRÊS DA MANHÃ. UM SINAL NUMA FREQUÊNCIA QUE NINGUÉM USA.',
            'ELE SE REPETE. LENTO E DELIBERADO.'],
            'DECIFRE ANTES QUE ELE SUMA.',
            'UMA PALAVRA: {word}. DEPOIS, NADA.',
            'O SINAL SE PERDE NA ESTÁTICA.', 'wireless'),
        beat('encode', 'RELATÓRIO', [
            'HALE PRECISA SABER DISSO AINDA HOJE.',
            'REPITA A PALAVRA EXATAMENTE COMO RECEBEU.'],
            'ENVIE A PALAVRA AO ALMIRANTADO.',
            "UMA LONGA PAUSA. HALE: 'NÃO CONTE A NINGUÉM.'",
            'A LINHA CAI.', 'wireless', echo=True),
    ]),
    dict(title='BACURAU', intro=[
        'HALE EXPLICA NUMA CARTA LACRADA, ENTREGUE EM MÃOS.',
        'BACURAU: UMA REDE QUE VENDE SEGREDOS NAVAIS A QUEM PAGAR MAIS.',
        'ELES FALAM À NOITE, E FALAM EM MORSE.'], beats=[
        beat('decode', 'O ENCONTRO', [
            'TRÁFEGO DO BACURAU NA FAIXA NOTURNA.',
            'UM LUGAR ESTÁ SENDO MENCIONADO.'],
            'DECIFRE O LOCAL DO ENCONTRO.',
            'O ENCONTRO É EM {word}. HALE MANDA HOMENS VIGIAREM.',
            'A MENSAGEM TERMINA. NINGUÉM VIGIA O ENCONTRO.', 'wireless'),
        beat('encode', 'O TREM NOTURNO', [
            'UM MENSAGEIRO COM PAPÉIS DO ALMIRANTADO ESTÁ NO TREM NOTURNO.',
            'HOMENS DO BACURAU EMBARCARAM NA ÚLTIMA PARADA.'],
            'TELEGRAFE À PRÓXIMA ESTAÇÃO PARA SEGURAR O TREM.',
            'O TREM É RETIDO. O MENSAGEIRO ESTÁ A SALVO.',
            'O TREM SEGUE. DE MANHÃ, OS PAPÉIS SUMIRAM.', 'rail'),
        beat('decode', 'UM NOME', [
            'O MENSAGEIRO OUVIU OS HOMENS BATEREM UM NOME NA PAREDE DO VAGÃO.',
            'ACHAVAM QUE NINGUÉM A BORDO SABIA LER AQUILO.'],
            'DECIFRE O NOME.',
            'O NOME É {word}. HALE FICA MUITO QUIETO.',
            'O MENSAGEIRO NÃO CONSEGUE LEMBRAR.', 'rail'),
    ]),
    dict(title='A LANTERNA', intro=[
        'SÓ TRÊS PESSOAS SABIAM QUE O MENSAGEIRO ESTAVA NAQUELE TREM.',
        'HALE. O MENSAGEIRO. E VOCÊ.',
        'ESTA NOITE, UMA LANTERNA PISCA NO PROMONTÓRIO.'], beats=[
        beat('decode', 'O PROMONTÓRIO', [
            'UMA LUZ NOS ROCHEDOS. ACESA. APAGADA. ACESA.',
            'ALGUÉM SINALIZA PARA UMA EMBARCAÇÃO AO LARGO.'],
            'LEIA A LANTERNA.',
            'A LANTERNA SOLETRA {word}. ELES SABEM QUE O POSTO ESCUTA.',
            'A LANTERNA SE APAGA.', 'harbour'),
        beat('encode', 'O CAPITÃO DO PORTO', [
            'UMA EMBARCAÇÃO VEM BUSCAR QUEM SEGURA A LANTERNA.',
            'O PORTO PODE SER FECHADO, SE O CAPITÃO FOR AVISADO A TEMPO.'],
            'ENVIE A ORDEM DE FECHAMENTO.',
            'A BARREIRA FECHA O PORTO. A EMBARCAÇÃO DÁ MEIA-VOLTA.',
            'A EMBARCAÇÃO VEM E VAI SEM SER VISTA.', 'harbour'),
        beat('decode', 'O BILHETE', [
            'MANHÃ. UM BILHETE DOBRADO SOB A PORTA DO POSTO.',
            'NÃO ESCRITO: FURADO EM PONTOS E TRAÇOS.'],
            'DECIFRE O BILHETE ANTES QUE A CHUVA O ESTRAGUE.',
            "O BILHETE DIZ {word}. ASSINADO: 'C'.",
            'A TINTA ESCORRE. O BILHETE SE PERDE.', 'wireless'),
    ]),
    dict(title='O TEMPORAL', intro=[
        'O PIOR TEMPORAL EM VINTE ANOS.',
        'A ENERGIA CAI À MEIA-NOITE. O POSTO FUNCIONA NAS BATERIAS.',
        'CADA MINUTO DE CARGA CONTA.'], beats=[
        beat('decode', 'SOCORRO', [
            'UM TRANSATLÂNTICO SE PERDEU NA NÉVOA PERTO DA PONTA. SINAL FRACO.',
            'O RADIOTELEGRAFISTA DE BORDO DESCREVE O QUE SE VÊ DA PONTE.'],
            'DECIFRE O PONTO DE REFERÊNCIA.',
            'ELES VEEM {word}. VOCÊ SABE EXATAMENTE ONDE FICA.',
            'O SINAL MORRE NA TEMPESTADE.', 'fog'),
        beat('encode', 'O RUMO', [
            'O NAVIO SEGUE DIRETO PARA AS PEDRAS.',
            'UMA CORREÇÃO, ANTES QUE AS BATERIAS ACABEM.'],
            'ENVIE O RUMO.',
            'O NAVIO VIRA. SUAS LUZES PASSAM EM SEGURANÇA PELA PONTA.',
            'AS BATERIAS MORREM NO MEIO DA PALAVRA.', 'fog'),
        beat('encode', 'O PACOTE', [
            'UM PACOTE CHEGOU COM A TEMPESTADE. ELE FAZ TIQUE-TAQUE.',
            'UM ARTEFATO DO BACURAU, COM UM MANIPULADOR TELEGRÁFICO COMO TRAVA.'],
            'BATA O CÓDIGO QUE O DESLIGA.',
            'O TIQUE-TAQUE PARA.',
            'A PRAIA SE ILUMINA POR UM INSTANTE. DEPOIS, ESCURIDÃO.', 'bomb'),
    ]),
    dict(title='CORRUÍRA', intro=[
        "O BILHETE ESTAVA ASSINADO 'C'.",
        'HALE ENFIM ADMITE: CORRUÍRA NOS PASSA INFORMAÇÕES DE DENTRO DO BACURAU.',
        'CORRUÍRA SÓ FALA COM VOCÊ.'], beats=[
        beat('encode', 'RECONHECIMENTO', [
            'CORRUÍRA SÓ RESPONDE À PALAVRA DE RECONHECIMENTO CERTA.',
            'UM CARRO DE PATRULHA DO BACURAU JÁ ESTÁ NA ESTRADA DA COSTA.'],
            'ENVIE A PALAVRA DE RECONHECIMENTO.',
            'UMA PAUSA. DEPOIS, DOIS PONTOS. CORRUÍRA ESTÁ OUVINDO.',
            'NENHUMA RESPOSTA. CORRUÍRA FICA EM SILÊNCIO.', 'road'),
        beat('decode', 'O QUE FOI LEVADO', [
            'CORRUÍRA TRANSMITE DEPRESSA, COM A MÃO TRÊMULA.',
            'O BACURAU LEVOU ALGO DE UM ARSENAL DA MARINHA.'],
            'DECIFRE O QUE FOI LEVADO.',
            "CORRUÍRA: '{word}. E A NOVA MÁQUINA DE CIFRA.'",
            'CORRUÍRA PARA NO MEIO DA FRASE.', 'wireless'),
        beat('decode', 'A ROTA', [
            'A MÁQUINA SERÁ VENDIDA NO EXTERIOR.',
            'CORRUÍRA CONHECE A ROTA.'],
            'DECIFRE A ROTA.',
            'ELA SAI POR {word}. O CERCO SE FECHA.',
            'ESTÁTICA. CORRUÍRA SUMIU POR ESTA NOITE.', 'wireless'),
    ]),
    dict(title='O ZEPELIM', intro=[
        'A MÁQUINA DE CIFRA ESTÁ A BORDO DE UM ZEPELIM RUMO AO CONTINENTE.',
        'NENHUM PASSAGEIRO LISTADO. NENHUMA CARGA DECLARADA.',
        'ELE CRUZA A COSTA ESTA NOITE.'], beats=[
        beat('decode', 'NAVEGAÇÃO', [
            'O ZEPELIM SE COMUNICA COM UMA ESTAÇÃO EM TERRA.',
            'ESTÁ INFORMANDO O PRÓXIMO PONTO DA ROTA.'],
            'DECIFRE O PONTO DA ROTA.',
            'PONTO {word}. AGORA VOCÊ CONHECE O CURSO DELE.',
            'O ZEPELIM PASSA EM SILÊNCIO.', 'wireless'),
        beat('encode', 'ESTAÇÃO FALSA', [
            'SE O CAPITÃO OUVIR O INDICATIVO ERRADO, O ZEPELIM VAI VIRAR.',
            'FINJA SER A ESTAÇÃO DELES.'],
            'ENVIE O INDICATIVO FALSO.',
            'O ZEPELIM MUDA DE CURSO, RUMO AO NOSSO CAMPO DE POUSO.',
            'O CAPITÃO NÃO SE DEIXA ENGANAR.', 'wireless'),
        beat('encode', 'INTERCEPTAR', [
            'DOIS BIPLANOS ESTÃO PRONTOS NO CAMPO DE POUSO.',
            'ELES NÃO DECOLAM SEM ORDENS.'],
            'ENVIE A ORDEM DE INTERCEPTAR.',
            'O ZEPELIM É FORÇADO A POUSAR INTACTO. O PORÃO ESTÁ VAZIO.',
            'O ZEPELIM DESAPARECE NAS NUVENS.', 'wireless'),
    ]),
    dict(title='SUBMERSO', intro=[
        'O ZEPELIM ERA UMA ISCA.',
        'A MÁQUINA FOI PARA O MAR,',
        'A BORDO DE UM SUBMARINO SEM BANDEIRA.'], beats=[
        beat('decode', 'HIDROFONE', [
            'O SUBMARINO SINALIZA AO NAVIO DE APOIO BATENDO NO CASCO.',
            'A ESTAÇÃO DE HIDROFONE REPASSA AS BATIDAS PARA VOCÊ.'],
            'DECIFRE AS BATIDAS.',
            'O SUBMARINO ENVIA {word}. ESTÁ SEGUINDO O NAVIO-CORREIO.',
            'AS BATIDAS PARAM. O SUBMARINO MERGULHA.', 'harbour'),
        beat('encode', 'O NAVIO-CORREIO', [
            'O NAVIO-CORREIO NÃO SABE QUE ESTÁ SENDO SEGUIDO.',
            'O SUBMARINO SE APROXIMA.'],
            'ENVIE O AVISO.',
            'O NAVIO-CORREIO MUDA DE CURSO E CORRE PARA O PORTO.',
            'O NAVIO-CORREIO NUNCA OUVIU VOCÊ.', 'harbour'),
        beat('encode', 'EMERGIR', [
            'UM CONTRATORPEDEIRO ENCURRALOU O SUBMARINO.',
            'QUER A MÁQUINA DE VOLTA, NÃO UM NAUFRÁGIO.'],
            'ENVIE A ORDEM PARA EMERGIR.',
            'O SUBMARINO EMERGE. A TRIPULAÇÃO SE RENDE. NENHUMA MÁQUINA A BORDO.',
            'O SUBMARINO ESCAPA NO ESCURO.', 'harbour'),
    ]),
    dict(title='QUEIMADO', intro=[
        'CORRUÍRA MANDA UMA LINHA EM PLENO DIA, CONTRA TODAS AS REGRAS:',
        "'ELES SABEM.'",
        'DEPOIS, NADA.'], beats=[
        beat('decode', 'ESCONDERIJO', [
            'HORAS DEPOIS. UM SINAL FRACO VINDO DO INTERIOR.',
            'CORRUÍRA SE ESCONDEU E ESTÁ MANDANDO O ENDEREÇO.'],
            'DECIFRE O ESCONDERIJO.',
            'CORRUÍRA ESTÁ EM {word}. AGUENTE FIRME, CORRUÍRA.',
            'O SINAL CAI.', 'wireless'),
        beat('encode', 'RESGATE', [
            'UM CARRO DO BACURAU JÁ ESTÁ A CAMINHO DO ESCONDERIJO.',
            'NOSSO MOTORISTA SÓ ESPERA A PALAVRA.'],
            'ENVIE A PALAVRA.',
            'FARÓIS NA ESTRADINHA. CORRUÍRA JÁ ESTÁ LONGE DALI.',
            'O CARRO DO BACURAU CHEGA PRIMEIRO.', 'road'),
        beat('decode', 'O AVISO DE CORRUÍRA', [
            'DO BANCO DE TRÁS, CORRUÍRA BATE UMA PALAVRA NUM RÁDIO PORTÁTIL.',
            'O CODINOME DE QUEM COMANDA O BACURAU.'],
            'DECIFRE O CODINOME.',
            'QUEM COMANDA O BACURAU É {word}. ALGUÉM DE DENTRO.',
            'O CARRO SAI DO ALCANCE.', 'road'),
    ]),
    dict(title='A BATIDA', intro=[
        'TODO TELEGRAFISTA TEM UMA BATIDA: UM RITMO TÃO PESSOAL QUANTO A LETRA.',
        'O BACURAU SEMPRE SOUBE O QUE O ALMIRANTADO SABIA.',
        'VOCÊ COMEÇA A OUVIR GRAVAÇÕES ANTIGAS.'], beats=[
        beat('decode', 'OS CILINDROS', [
            'CILINDROS DE CERA COM O TRÁFEGO DO ALMIRANTADO DO MÊS PASSADO.',
            'POR BAIXO DAS MENSAGENS DE ROTINA, UMA SEGUNDA MÃO TRANSMITE.'],
            'DECIFRE A TRANSMISSÃO ESCONDIDA.',
            'DIZ {word}. VOCÊ CONHECE ESSA BATIDA. É HALE.',
            'O CILINDRO RACHA.', 'wireless'),
        beat('encode', 'NÃO CONFIE EM NINGUÉM', [
            'HALE CONTROLA AS LINHAS DO ALMIRANTADO.',
            'SÓ SE PODE CONFIAR EM CORRUÍRA AGORA.'],
            'ENVIE A PALAVRA DE ALERTA A CORRUÍRA.',
            "CORRUÍRA RESPONDE: 'ENTENDIDO. NÃO CONFIE EM NINGUÉM.'",
            'A MENSAGEM SAI NUMA FAIXA ABERTA. HALE ESCUTA.', 'wireless'),
        beat('decode', 'HALE CHAMA', [
            'A LINHA DO ALMIRANTADO ABRE. HALE ESTÁ CHAMANDO. MUITO CALMO.',
            'CALMO DEMAIS. HÁ UMA PALAVRA-CÓDIGO ESCONDIDA NO TRÁFEGO.'],
            'DECIFRE A PALAVRA-CÓDIGO.',
            'A PALAVRA É {word}. SIGNIFICA: SILENCIAR O POSTO SETE.',
            'HALE FECHA A LINHA.', 'wireless'),
    ]),
    dict(title='SEM ALIADOS', intro=[
        'AGORA O ALMIRANTADO DIZ QUE VOCÊ ABANDONOU O POSTO.',
        'UM AVIÃO DO BACURAU ESTÁ VINDO PARA O POSTO.',
        'O CAMPO DE POUSO AINDA PODE OUVIR UM CHAMADO HONESTO.'], beats=[
        beat('encode', 'PEDIDO DE SOCORRO', [
            'O AVIÃO JÁ ESTÁ SOBRE O MAR.',
            'O CAMPO DE POUSO É SUA ÚNICA CHANCE.'],
            'ENVIE O PEDIDO DE SOCORRO.',
            'DOIS BIPLANOS SOBEM PARA ENFRENTÁ-LO. O INTRUSO RECUA.',
            'NINGUÉM RESPONDE.', 'air'),
        beat('decode', 'O PILOTO', [
            'O BACURAU BLOQUEIA A FAIXA. UM DOS PILOTOS AINDA CONSEGUE PASSAR.',
            'VOCÊ PRECISA SABER QUEM ESTÁ LÁ EM CIMA.'],
            'DECIFRE O INDICATIVO DO PILOTO.',
            'INDICATIVO {word}. UM ALIADO. O CÉU ESTÁ GARANTIDO.',
            'A INTERFERÊNCIA ENGOLE TUDO.', 'air'),
        beat('encode', 'A ISCA', [
            'HALE ACHA QUE ACABOU PARA VOCÊ.',
            'ENVIE ALGO EM QUE HALE VAI ACREDITAR: UMA RENDIÇÃO.'],
            'ENVIE A PALAVRA DE RENDIÇÃO.',
            "HALE MORDE A ISCA: 'VENHA AO POSTO. SEM NINGUÉM.'",
            'HALE DESCONFIA DA ARMADILHA.', 'wireless'),
    ]),
    dict(title='O ARTEFATO', intro=[
        'HALE NÃO VEIO SEM COMPANHIA.',
        'UM ARTEFATO FOI DEIXADO SOB A SALA DO TRANSMISSOR.',
        'O RELÓGIO JÁ ESTÁ CORRENDO.'], beats=[
        beat('decode', 'O DIAGRAMA', [
            'CORRUÍRA TEM O DIAGRAMA.',
            'CORRUÍRA TRANSMITE O PRIMEIRO PASSO, DEVAGAR.'],
            'DECIFRE O PRIMEIRO FIO.',
            'O FIO {word} ESTÁ CORTADO. SUAS MÃOS TREMEM.',
            'VOCÊ ERRA. O RELÓGIO ACELERA.', 'bomb'),
        beat('encode', 'O MANIPULADOR', [
            'O ARTEFATO TEM SEU PRÓPRIO MANIPULADOR TELEGRÁFICO.',
            'ELE QUER UM CÓDIGO, ENVIADO SEM ERROS.'],
            'ENVIE O CÓDIGO DE DESARME.',
            'A PRIMEIRA TRAVA SE SOLTA. FALTA UMA.',
            'O RELÓGIO NÃO PARA.', 'bomb'),
        beat('encode', 'ÚLTIMA TRAVA', [
            'UMA TRAVA. O RELÓGIO CONTA EM SEGUNDOS.',
            'LÁ FORA, HALE ESPERA OUVIR A EXPLOSÃO.'],
            'ENVIE O CÓDIGO FINAL.',
            'O RELÓGIO PARA. VOCÊ LEMBRA DE RESPIRAR.',
            'O POSTO SETE DEIXOU DE EXISTIR.', 'bomb'),
    ]),
    dict(title='SINAL FINAL', intro=[
        'HALE CORRE PARA O PORTO.',
        'O MUNDO PRECISA SABER O QUE HALE FEZ.',
        'UM TRANSMISSOR. UMA NOITE. TODAS AS LETRAS QUE VOCÊ SABE.'], beats=[
        beat('decode', 'A FUGA', [
            'HALE SINALIZA PARA UMA EMBARCAÇÃO À ESPERA.',
            'A BATIDA DE HALE ESTÁ TRÊMULA AGORA.'],
            'DECIFRE O PLANO.',
            'HALE PRETENDE FUGIR PARA {word}. NÃO ESTA NOITE.',
            'A EMBARCAÇÃO SOLTA AS AMARRAS.', 'harbour'),
        beat('encode', 'A BARREIRA', [
            'O CAPITÃO DO PORTO AINDA RECEBE ORDENS PELO TELÉGRAFO.',
            'A BARREIRA PODE SER FECHADA UMA ÚLTIMA VEZ.'],
            'ENVIE A ORDEM DE FECHAMENTO.',
            'A BARREIRA SE FECHA. HALE É PRESO NO CAIS.',
            'A EMBARCAÇÃO DEIXA O PORTO.', 'harbour'),
        beat('encode', 'A TODAS AS ESTAÇÕES', [
            'TODAS AS ESTAÇÕES DA COSTA ESTÃO ESCUTANDO ESTA NOITE.',
            'CONTE A ELAS.'],
            'ENVIE A PALAVRA FINAL.',
            'A MENSAGEM CHEGA A TODAS AS ESTAÇÕES. O BACURAU ACABOU.',
            'O TRANSMISSOR FALHA. ENVIE DE NOVO.', 'wireless'),
    ]),
]
ENDING_PT = [
    'AMANHECE NA COSTA. O TEMPORAL PASSOU.',
    'CORRUÍRA ENVIA UM ÚLTIMO SINAL: PONTO PONTO PONTO TRAÇO PONTO TRAÇO.',
    'SK. FIM DO SERVIÇO.',
    'O POSTO SETE ENCERRA AS TRANSMISSÕES.',
]
WIN_BANNERS_PT = ['RECEBIDO', 'CONFIRMADO', 'ENTENDIDO']
LOSE_BANNERS_PT = ['TARDE DEMAIS', 'SEM RESPOSTA', 'SINAL PERDIDO']

LANGS = ['en', 'pt']
WORDS = {'en': WORDS_EN, 'pt': WORDS_PT}
CHAPTERS = {'en': CHAPTERS_EN, 'pt': CHAPTERS_PT}
ENDING = {'en': ENDING_EN, 'pt': ENDING_PT}
WIN_BANNERS = {'en': WIN_BANNERS_EN, 'pt': WIN_BANNERS_PT}
LOSE_BANNERS = {'en': LOSE_BANNERS_EN, 'pt': LOSE_BANNERS_PT}

UI = {
    'en': {
        'size': 'MAKE THE TERMINAL AT LEAST 80x24',
        'score': 'SCORE {score:06d}', 'chapter_hud': 'CHAPTER {n:02d}/{total}', 'best': 'BEST {best:06d}',
        'send': 'SEND · ', 'receive': 'RECEIVE · ', 'message': 'MESSAGE {n}/3',
        'hints_on': 'HINTS ON  -{cost}', 'incorrect': 'INCORRECT.  {ch} IS {pattern}',
        'sent_need': 'SENT {got} {sent}   NEED {need} {needed}',
        'key': ' KEY ', 'lamp': ' LAMP ',
        'title_big': 'MORSE CODE', 'subtitle': 'STATION SEVEN  ·  1936',
        'tap_hold': 'TAP SPACE = DIT {dot}        HOLD SPACE = DAH {dah}',
        'menu_begin': '[ENTER] BEGIN', 'menu_continue': '[C] CONTINUE FROM CHAPTER {n}',
        'menu_rest': '[F] PRACTICE   [L] LANGUAGE   [Q] QUIT',
        'chapter_label': 'CHAPTER {n}', 'first_letters': 'YOUR FIRST LETTERS', 'new_letters': 'NEW LETTERS',
        'try_them': 'TRY THEM ▸ ', 'enter_begin': '[ENTER] BEGIN',
        'chapter_help': 'TAP / HOLD SPACE TO PRACTISE   [TAB] HEAR THEM AGAIN',
        'brief_line': 'CHAPTER {n} · {title}', 'code_word': 'CODE WORD:  {word}', 'ready': '[ENTER] READY',
        'encode_help': 'TAP SPACE = DIT •    HOLD SPACE = DAH ━    [TAB] HINT    [ESC] QUIT',
        'no_lamp': 'NO LAMP FROM HERE ON. LISTEN.',
        'decode_help': 'TYPE THE LETTERS YOU HEAR    [TAB] REPEAT    [ESC] QUIT',
        'time_bonus': '+{bonus} TIME BONUS', 'lives_left': 'LIVES LEFT: {n}. TRY AGAIN.',
        'no_lives': 'NO LIVES LEFT.', 'continue': '[ENTER] CONTINUE',
        'practice': 'PRACTICE', 'free_help': 'TAP = DIT  ·  HOLD = DAH  ·  [BKSP] ERASE  ·  [ESC] BACK',
        'over_big': 'SIGNAL LOST', 'over_line': 'STATION SEVEN HAS GONE SILENT.',
        'final_score': 'FINAL SCORE {score:06d}', 'new_best': 'NEW BEST',
        'over_continue': 'CONTINUE FROM CHAPTER {n} ON THE TITLE SCREEN.',
        'end_big': 'END OF WORK',
    },
    'pt': {
        'size': 'AUMENTE O TERMINAL PARA PELO MENOS 80x24',
        'score': 'PONTOS {score:06d}', 'chapter_hud': 'CAPÍTULO {n:02d}/{total}', 'best': 'RECORDE {best:06d}',
        'send': 'ENVIAR · ', 'receive': 'RECEBER · ', 'message': 'MENSAGEM {n}/3',
        'hints_on': 'DICAS LIGADAS  -{cost}', 'incorrect': 'ERRADO.  {ch} É {pattern}',
        'sent_need': 'ENVIOU {got} {sent}   ERA {need} {needed}',
        'key': ' TECLA ', 'lamp': ' LUZ ',
        'title_big': 'CÓDIGO MORSE', 'subtitle': 'POSTO SETE  ·  1936',
        'tap_hold': 'TOQUE O ESPAÇO = PONTO {dot}      SEGURE O ESPAÇO = TRAÇO {dah}',
        'menu_begin': '[ENTER] COMEÇAR', 'menu_continue': '[C] CONTINUAR DO CAPÍTULO {n}',
        'menu_rest': '[P] PRATICAR   [L] IDIOMA   [Q] SAIR',
        'chapter_label': 'CAPÍTULO {n}', 'first_letters': 'SUAS PRIMEIRAS LETRAS', 'new_letters': 'LETRAS NOVAS',
        'try_them': 'EXPERIMENTE ▸ ', 'enter_begin': '[ENTER] COMEÇAR',
        'chapter_help': 'TOQUE / SEGURE O ESPAÇO PARA PRATICAR   [TAB] OUVIR DE NOVO',
        'brief_line': 'CAPÍTULO {n} · {title}', 'code_word': 'PALAVRA-CÓDIGO:  {word}', 'ready': '[ENTER] PRONTO',
        'encode_help': 'TOQUE = PONTO •    SEGURE = TRAÇO ━    [TAB] DICA    [ESC] SAIR',
        'no_lamp': 'DAQUI EM DIANTE, SEM LUZ. ESCUTE.',
        'decode_help': 'DIGITE AS LETRAS QUE OUVIR    [TAB] REPETIR    [ESC] SAIR',
        'time_bonus': '+{bonus} BÔNUS DE TEMPO', 'lives_left': 'VIDAS RESTANTES: {n}. TENTE DE NOVO.',
        'no_lives': 'SEM VIDAS.', 'continue': '[ENTER] CONTINUAR',
        'practice': 'PRÁTICA',
        'free_help': 'TOQUE = PONTO  ·  SEGURE = TRAÇO  ·  [BKSP] APAGAR  ·  [ESC] VOLTAR',
        'over_big': 'SINAL PERDIDO', 'over_line': 'O POSTO SETE SILENCIOU.',
        'final_score': 'PONTUAÇÃO FINAL {score:06d}', 'new_best': 'NOVO RECORDE',
        'over_continue': 'CONTINUE DO CAPÍTULO {n} NA TELA INICIAL.',
        'end_big': 'FIM DA ESCUTA',
    },
}

# 5x7 font, drawn with half blocks: one cell wide, half a cell tall per pixel.
_FONT = """
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .###. #...# #.... #.... #.... #...# .###.
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .###. #...# #.... #.### #...# #...# .####
H #...# #...# #...# ##### #...# #...# #...#
I .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.
J ..### ...#. ...#. ...#. ...#. #..#. .##..
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# #...# ##..# #.#.# #..## #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# #.#.# .#.#.
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ##### ...#. ..#.. ...#. ....# #...# .###.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 ..##. .#... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ...#. .##..
! ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..
? .###. #...# ....# ...#. ..#.. ..... ..#..
_ ..... ..... ..... ..... ..... ..... #####
"""
FONT = {line[0]: line[2:].split() for line in _FONT.strip().splitlines()}


def pretty(pattern):
    return ' '.join(DOT if e == '.' else DAH for e in pattern)


def unlocked(chapter):
    return ''.join(LEVELS[:chapter])


def pick_word(chapter, lang):
    known = set(unlocked(chapter))
    new = set(LEVELS[chapter - 1])
    pool = [w for w in WORDS[lang] if set(w) <= known and len(w) <= 3 + chapter]
    fresh = [w for w in pool if set(w) & new]
    if fresh and random.random() < .7:
        return random.choice(fresh)
    if pool:
        return random.choice(pool)
    return ''.join(random.choice(sorted(known)) for _ in range(3))


# --------------------------------------------------------------------- keyer

class Keyer:
    """Turns a stream of space-key events into dit/dah patterns.

    One event alone = tap (dit). A tap followed ~repeat-delay later by a burst of
    repeats spaced ~repeat-interval apart = hold (dah). Two events with no burst
    after them were two quick taps.
    """

    def __init__(self, delay, interval, letter_gap):
        self.first_repeat = delay + .08
        self.repeat_gap = interval * 2 + .05
        self.letter_gap = max(letter_gap, self.first_repeat + .1)
        self.ev, self.pattern, self.last = [], '', 0.0

    def _settle(self, now):
        ev = self.ev
        while ev:
            gap = now - ev[-1]
            if len(ev) == 1:
                if gap <= self.first_repeat:
                    return
                self.pattern += '.'
                ev.clear()
            elif len(ev) == 2:
                if gap <= self.repeat_gap:
                    return
                self.pattern += '.'
                del ev[0]  # first was a tap; judge the second as its own press
            else:
                if gap <= self.repeat_gap:
                    return
                self.pattern += '-'
                ev.clear()

    def press(self, t):
        self._settle(t)
        self.ev.append(t)
        self.last = t

    blip_on_press = True  # tone can't start for real until the hold is proven

    def release(self, t):
        pass  # terminals never report it

    def holding(self):
        return len(self.ev) >= 3

    def sounding(self):
        return self.holding()

    def live(self, now):
        return self.pattern + ('-' if self.holding() else '.' if self.ev else '')

    def tick(self, now):
        """Return a finished letter pattern once the letter gap has passed."""
        self._settle(now)
        if not self.ev and self.pattern and now - self.last > self.letter_gap:
            pattern, self.pattern = self.pattern, ''
            return pattern


class PressKeyer:
    """Keyer fed real press/release events (evdev): held >= dah_time is a dah."""

    blip_on_press = False

    def __init__(self, dah_time, letter_gap):
        self.dah_time, self.letter_gap = dah_time, letter_gap
        self.ev, self.pattern, self.last = [], '', 0.0

    def press(self, t):
        if not self.ev:
            self.ev, self.last = [t], t

    def release(self, t):
        if self.ev:
            self.pattern += '-' if t - self.ev[0] >= self.dah_time else '.'
            self.ev, self.last = [], t

    def sounding(self):
        return bool(self.ev)

    def live(self, now):
        if not self.ev:
            return self.pattern
        return self.pattern + ('-' if now - self.ev[0] >= self.dah_time else '.')

    def tick(self, now):
        if not self.ev and self.pattern and now - self.last > self.letter_gap:
            pattern, self.pattern = self.pattern, ''
            return pattern


KEY_SPACE, EV_KEY, INPUT_EVENT = 57, 1, struct.Struct('llHHi')


def open_keyboards():
    """Non-blocking fds for every input device that has a space key.

    Includes virtual keyboards (keyd, kanata...), which grab the physical ones
    and re-emit every key from a device with no /dev/input/by-path entry.
    """
    fds = []
    try:
        with open('/proc/bus/input/devices') as f:
            blocks = f.read().split('\n\n')
    except OSError:
        return fds
    for block in blocks:
        handlers = next((ln for ln in block.splitlines() if ln.startswith('H: Handlers=')), '')
        keys = next((ln for ln in block.splitlines() if ln.startswith('B: KEY=')), '')
        events = [h for h in handlers.split('=', 1)[-1].split() if h.startswith('event')]
        bitmap = keys.split('=', 1)[-1].split()
        if not events or not bitmap:
            continue
        # KEY= is a list of 64-bit hex words, most significant first
        if not int(''.join(w.zfill(16) for w in bitmap), 16) >> KEY_SPACE & 1:
            continue
        try:
            fds.append(os.open(f'/dev/input/{events[0]}', os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            pass
    return fds


def read_space_events(fd):
    """Yield True for space down, False for space up (autorepeat ignored)."""
    try:
        data = os.read(fd, INPUT_EVENT.size * 64)
    except OSError:
        return
    for off in range(0, len(data) - INPUT_EVENT.size + 1, INPUT_EVENT.size):
        _, _, kind, code, value = INPUT_EVENT.unpack_from(data, off)
        if kind == EV_KEY and code == KEY_SPACE and value in (0, 1):
            yield value == 1


# --------------------------------------------------------------------- audio

RATE, KEY_HZ, SIG_HZ = 11025, 700, 600


def square(freq, dur, vol=.2):
    phase = 0.0
    for _ in range(int(dur * RATE)):
        phase = (phase + freq / RATE) % 1
        yield vol if phase < .5 else -vol


def slide(f0, f1, dur, vol=.2):
    n, phase = int(dur * RATE), 0.0
    for i in range(n):
        phase = (phase + (f0 + (f1 - f0) * i / n) / RATE) % 1
        yield vol if phase < .5 else -vol


def noise(dur, vol=.3, hold=12):
    """Sample-and-hold noise with a linear fade: the TIA rumble."""
    n, v = int(dur * RATE), 0.0
    for i in range(n):
        if i % hold == 0:
            v = random.uniform(-vol, vol)
        yield v * (1 - i / n)


def rest(dur):
    return itertools.repeat(0.0, int(dur * RATE))


def notes(freqs, dur=.1, vol=.15):
    return itertools.chain(*(square(f, dur, vol) if f else rest(dur) for f in freqs))


def schedule(word, wpm, farnsworth):
    """On-intervals (start, end, element, letter_index) for a word, plus total length."""
    dot, t, on = 1.2 / wpm, 0.0, []
    for li, ch in enumerate(word):
        for e in MORSE[ch]:
            d = dot if e == '.' else 3 * dot
            on.append((t, t + d, e, li))
            t += d + dot
        t += dot * (3 * farnsworth - 1)
    return on, t


def signal(on):
    prev = 0.0
    for s, e, _, _ in on:
        yield from rest(s - prev)
        yield from square(SIG_HZ, e - s, .22)
        prev = e


class Audio:
    """Two queued channels (fx, sig) plus the player's sidetone, streamed to aplay."""

    def __init__(self, volume):
        self.volume = volume
        self.lock = threading.Lock()
        self.queues = {'fx': [], 'sig': []}
        self.key_on, self.blip, self.phase = False, 0, 0.0
        try:
            self.proc = subprocess.Popen(
                ['aplay', '-q', '-t', 'raw', '-f', 'U8', '-r', str(RATE), '-c', '1',
                 '--buffer-time=30000', '--period-time=7500'],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                env={**os.environ, 'PIPEWIRE_LATENCY': f'128/{RATE}'})
        except OSError:
            self.proc = None  # no aplay: play silently
            return
        threading.Thread(target=self._stream, daemon=True).start()

    def play(self, gen, channel='fx', cut=False):
        with self.lock:
            if cut:
                self.queues[channel].clear()
            self.queues[channel].append(gen)

    def stop_signal(self):
        with self.lock:
            self.queues['sig'].clear()

    def _next_sample(self, queue):
        while queue:
            v = next(queue[0], None)
            if v is not None:
                return v
            queue.pop(0)
        return 0.0

    def _stream(self):
        # A pipe holds ~6 s of 11 kHz U8 audio; writing freely queues the sidetone
        # behind all of it. Only top up when less than LEAD is waiting in the pipe.
        fd, lead = self.proc.stdin.fileno(), int(.02 * RATE)
        while True:
            try:
                queued = struct.unpack('i', fcntl.ioctl(fd, termios.FIONREAD, b'\0\0\0\0'))[0]
            except OSError:
                return
            if queued > lead:
                time.sleep(.003)
                continue
            buf = bytearray(64)
            with self.lock:
                for i in range(64):
                    v = self._next_sample(self.queues['fx']) + self._next_sample(self.queues['sig'])
                    if self.key_on or self.blip > 0:
                        self.blip -= 1
                        self.phase = (self.phase + KEY_HZ / RATE) % 1
                        v += .25 if self.phase < .5 else -.25
                    buf[i] = max(0, min(255, int(128 + v * 100 * self.volume)))
            try:
                os.write(fd, buf)
            except OSError:
                return

    def close(self):
        if self.proc:
            self.proc.kill()


# --------------------------------------------------------------------- drawing

class Canvas:
    """Full-terminal cell grid; drawing coordinates are an 80x24 area centred in it."""

    def __init__(self, width, height):
        self.W, self.H = width, height
        self.ox, self.oy = (width - 80) // 2, (height - 24) // 2
        self.cells = [[(' ', PAPER, INK)] * width for _ in range(height)]

    def _at(self, x, y):
        X, Y = x + self.ox, y + self.oy
        return (X, Y) if 0 <= X < self.W and 0 <= Y < self.H else None

    def put(self, x, y, text, fg=PAPER, bg=None):
        for i, ch in enumerate(text):
            p = self._at(x + i, y)
            if p:
                X, Y = p
                self.cells[Y][X] = (ch, fg, bg or self.cells[Y][X][2])

    def bg_at(self, x, y):
        p = self._at(x, y)
        return self.cells[p[1]][p[0]][2] if p else INK

    def band(self, y0, y1, bg):
        for y in range(y0, y1):
            Y = y + self.oy
            if 0 <= Y < self.H:
                self.cells[Y] = [(' ', PAPER, bg)] * self.W

    def center(self, y, text, fg=PAPER, bg=None):
        self.put(40 - len(text) // 2, y, text, fg, bg)

    def render(self):
        out, last = [], None
        for Y, row in enumerate(self.cells):
            out.append(f'\x1b[{Y + 1};1H')
            for ch, fg, bg in row:
                if (fg, bg) != last:
                    out.append('\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm' % (fg + bg))
                    last = (fg, bg)
                out.append(ch)
        return ''.join(out)


def bigw(text):
    return len(text) * 6 - 1


def big(c, x, y, text, color):
    """5x7 pixel font, 4 cells tall."""
    for n, ch in enumerate(text):
        glyph = FONT.get(ch) or FONT.get(unicodedata.normalize('NFD', ch)[0])
        if not glyph:
            continue
        rows = glyph + ['.....']
        for r in range(0, 8, 2):
            for i in range(5):
                a, b = rows[r][i] == '#', rows[r + 1][i] == '#'
                X, Y = x + n * 6 + i, y + r // 2
                if a:
                    c.put(X, Y, '▀', color, color if b else c.bg_at(X, Y))
                elif b:
                    c.put(X, Y, '▄', color)


def big_center(c, y, text, color):
    big(c, 40 - bigw(text) // 2, y, text, color)


def sprite(c, x, y, rows, flicker=False, faded=False):
    """Pixel art packed two rows per cell with half blocks; '.' is transparent."""
    if len(rows) % 2:
        rows = rows + ['.' * len(rows[0])]

    def color(p, under):
        if p == '.':
            return under
        if faded:
            return FAINT
        if flicker and p in 'OY':
            p = 'Y' if p == 'O' else 'O'
        return PAL[p]

    for r in range(0, len(rows), 2):
        for i, (a, b) in enumerate(zip(rows[r], rows[r + 1])):
            if a == '.' and b == '.':
                continue
            under = c.bg_at(x + i, y + r // 2)
            c.put(x + i, y + r // 2, '▀', color(a, under), color(b, under))


# --------------------------------------------------------------------- game

class Game:
    def __init__(self, args, audio):
        self.args, self.audio = args, audio
        self.save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.save.json')
        try:
            with open(self.save_path) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        self.hi, self.saved_chapter = saved.get('hi', 0), saved.get('chapter', 1)
        self.lang = saved.get('lang') if saved.get('lang') in LANGS else 'en'
        self.score = self.lives = self.combo = self.beat_no = 0
        self.chapter, self.mode, self.free_text, self.last_word = 1, 'encode', '', None
        self.msg_until, self.device_seen = 0.0, False
        self.set_state('lang', time.monotonic())

    def write_save(self):
        try:
            with open(self.save_path, 'w') as f:
                json.dump({'hi': self.hi, 'chapter': self.saved_chapter, 'lang': self.lang}, f)
        except OSError:
            pass

    def text(self, key, **values):
        return UI[self.lang][key].format(**values)

    @property
    def chapters(self):
        return CHAPTERS[self.lang]

    # ---- state changes

    def set_state(self, state, now):
        self.state, self.t_state, self.typed_all = state, now, False
        a = self.args
        if a.evdev:
            self.keyer = PressKeyer(a.dah_time, a.letter_gap)
        else:
            self.keyer = Keyer(a.repeat_delay, a.repeat_interval, a.letter_gap)
        self.audio.key_on = False

    def to_title(self, now):
        self.audio.stop_signal()
        self.set_state('title', now)

    def start_game(self, chapter, now):
        self.score, self.lives, self.combo, self.chapter, self.last_word = 0, 3, 0, chapter, None
        self.open_chapter(now)

    def open_chapter(self, now):
        if self.chapter > len(self.chapters):
            return self.finish(now)
        self.saved_chapter = max(self.saved_chapter, self.chapter)
        self.write_save()
        self.beat_no, self.free_text = 0, ''
        self.new_letters = LEVELS[self.chapter - 1]
        self.set_state('chapter', now)
        self.play_new_letters(delay=2.5)

    def play_new_letters(self, delay=0.0):
        gens = [rest(delay)]
        for ch in self.new_letters:
            gens += [signal(schedule(ch, 15, 1)[0]), rest(.8)]
        self.audio.play(itertools.chain(*gens), 'sig', cut=True)

    def open_beat(self, now):
        self.beat = self.chapters[self.chapter - 1]['beats'][self.beat_no]
        self.mode = self.beat['mode']
        echo = self.beat['echo'] and self.last_word
        self.word = self.last_word if echo else pick_word(self.chapter, self.lang)
        self.audio.stop_signal()
        self.set_state('brief', now)

    def start_play(self, now):
        self.set_state('play', now)
        self.pos, self.hint = 0, self.chapter <= 3
        ch, n = self.chapter, len(self.word)
        if self.mode == 'decode':
            wpm, farnsworth = min(12 + ch, 24), max(1.0, 3.6 - .3 * ch)
            self.on, sig_len = schedule(self.word, wpm, farnsworth)
            self.radio_only = ch > 4
            self.replay(now, lead=.8)
            budget = sig_len + .8 + n * max(1.8, 4.5 - .3 * ch)
        else:
            budget = n * max(2.2, 7 - .45 * ch)
        self.t_total = budget + 2
        self.t_end = now + self.t_total
        self.next_beat = now

    def replay(self, now, lead=.3):
        self.sig_t0 = now + lead
        self.audio.play(itertools.chain(rest(lead), signal(self.on)), 'sig', cut=True)

    def progress(self, now):
        return min(1.0, max(0.0, 1 - (self.t_end - now) / self.t_total))

    def say(self, text, col, now):
        self.msg, self.msg_col, self.msg_until = text, col, now + 2.5

    def correct(self, now):
        self.pos += 1
        self.combo += 1
        pts = 10 * self.chapter * min(self.combo, 8)
        self.score += pts
        self.say(f'+{pts}', GO, now)
        self.audio.play(square(1047, .04, .08))
        if self.pos == len(self.word):
            self.win(now)

    def wrong(self, text, now):
        self.combo = 0
        self.t_end -= self.t_total * .1
        self.say(text, ALERT, now)
        self.audio.play(square(150, .12, .15))

    def win(self, now):
        self.p_end = self.progress(now)
        self.bonus = int(max(0, self.t_end - now) * 10 * self.chapter) + 100 * self.chapter
        self.score += self.bonus
        self.banner = random.choice(WIN_BANNERS[self.lang])
        if self.mode == 'decode':
            self.last_word = self.word
        self.audio.stop_signal()
        self.set_state('win', now)
        self.audio.play(notes([523, 659, 784], .12, .1), cut=True)

    def lose(self, now):
        self.p_end, self.lives, self.combo = 1.0, self.lives - 1, 0
        self.banner = random.choice(LOSE_BANNERS[self.lang])
        self.audio.stop_signal()
        self.set_state('lose', now)
        self.audio.play(noise(1.4, .25, 40), cut=True)

    def after_result(self, now):
        if self.state == 'lose':
            return self.game_over(now) if self.lives <= 0 else self.open_beat(now)
        self.beat_no += 1
        if self.beat_no >= 3:
            self.chapter += 1
            return self.open_chapter(now)
        self.open_beat(now)

    def record_score(self):
        self.new_hi = self.score > self.hi
        self.hi = max(self.hi, self.score)
        self.write_save()

    def game_over(self, now):
        self.record_score()
        self.set_state('over', now)
        self.audio.play(slide(300, 80, 1.0, .12), cut=True)

    def finish(self, now):
        self.saved_chapter = 1
        self.record_score()
        self.set_state('ending', now)
        self.new_letters = ''
        sk = signal(schedule('S', 12, 1)[0] + [(s + .6, e + .6, x, i) for s, e, x, i in schedule('K', 12, 1)[0]])
        self.audio.play(itertools.chain(rest(4), sk), 'sig', cut=True)

    # ---- input

    def keying(self):
        return self.state in ('free', 'chapter') or (self.state == 'play' and self.mode == 'encode')

    def space_down(self, now):
        if not self.keying():
            return
        self.keyer.press(now)
        if not self.keyer.blip_on_press:
            self.audio.key_on = True
        elif not self.keyer.holding():
            self.audio.blip = int(.09 * RATE)

    def space_up(self, now):
        if self.keying():
            self.keyer.release(now)
            self.audio.key_on = self.keyer.sounding()

    def device_space(self, down, now):
        self.device_seen = True
        self.space_down(now) if down else self.space_up(now)

    def key(self, k, now):
        s = self.state
        if k == 'ESC':
            if s in ('title', 'lang'):
                raise SystemExit
            return self.to_title(now)
        if k == ' ':
            if self.args.evdev and not self.device_seen:
                # the terminal saw a space the devices didn't: fall back to autorepeat
                a = self.args
                a.evdev = False
                self.keyer = Keyer(a.repeat_delay, a.repeat_interval, a.letter_gap)
            if not self.args.evdev:  # with evdev, the device events drive the key
                self.space_down(now)
            return
        enter = k in ('\r', '\n')
        if enter and s in ('chapter', 'brief', 'ending') and not self.typed_all:
            self.t_state -= 100  # skip the typewriter
            return
        if s == 'lang':
            if k in ('1', '2'):
                self.lang = LANGS[int(k) - 1]
            elif enter:
                self.write_save()
                self.to_title(now)
        elif s == 'title':
            if enter:
                self.start_game(1, now)
            elif k in ('c', 'C') and self.saved_chapter > 1:
                self.start_game(self.saved_chapter, now)
            elif k in ('f', 'F', 'p', 'P'):
                self.set_state('free', now)
                self.free_text = ''
            elif k in ('l', 'L'):
                self.set_state('lang', now)
            elif k in ('q', 'Q'):
                raise SystemExit
        elif s == 'chapter':
            if enter:
                self.open_beat(now)
            elif k == '\t':
                self.play_new_letters()
        elif s == 'brief' and enter:
            self.start_play(now)
        elif s in ('win', 'lose') and enter and now - self.t_state > 1.0:
            self.after_result(now)
        elif s in ('over', 'ending') and enter and now - self.t_state > 1.5:
            self.to_title(now)
        elif s == 'free' and k in ('\x7f', '\x08'):
            self.free_text = self.free_text[:-1]
        elif s == 'play':
            if k == '\t':
                if self.mode == 'decode':
                    self.replay(now)
                elif not self.hint:
                    cost = 25 * self.chapter
                    self.hint, self.score = True, max(0, self.score - cost)
                    self.say(self.text('hints_on', cost=cost), AMBER, now)
            elif self.mode == 'decode' and k.upper() in MORSE:
                ch, need = k.upper(), self.word[self.pos]
                if ch == need:
                    self.correct(now)
                else:
                    self.wrong(self.text('incorrect', ch=ch, pattern=pretty(MORSE[ch])), now)

    # ---- time

    def tick(self, now):
        s = self.state
        if s in ('free', 'chapter'):
            pattern = self.keyer.tick(now)
            if pattern:
                self.free_text = (self.free_text + DECODE.get(pattern, '?'))[-60:]
            idle = not self.keyer.ev and not self.keyer.pattern
            if idle and self.free_text[-1:] not in ('', ' ') and now - self.keyer.last > self.args.letter_gap * 2.5:
                self.free_text += ' '
        elif s == 'play':
            if self.mode == 'encode':
                pattern = self.keyer.tick(now)
                if pattern:
                    need, got = self.word[self.pos], DECODE.get(pattern)
                    if got == need:
                        self.correct(now)
                    else:
                        self.wrong(self.text('sent_need', got=got or '??', sent=pretty(pattern),
                                           need=need, needed=pretty(MORSE[need])), now)
            if self.state == 'play':
                left = (self.t_end - now) / self.t_total
                if now >= self.t_end:
                    self.lose(now)
                elif left < .3 and now >= self.next_beat:
                    # heartbeat in the last stretch: the only timer sound
                    self.audio.play(itertools.chain(square(55, .05, .2), rest(.12), square(50, .05, .15)))
                    self.next_beat = now + (1.0 if left > .15 else .6)
        self.audio.key_on = self.keying() and self.keyer.sounding()

    # ---- drawing

    def draw(self, now):
        width, height = os.get_terminal_size()
        c = Canvas(width, height)
        if width < 80 or height < 24:
            c.ox = c.oy = 0
            c.put(0, 0, self.text('size'), AMBER)
            return c
        getattr(self, 'draw_' + self.state)(c, now)
        return c

    def typewriter(self, c, y, lines, now, col=PAPER):
        budget = int((now - self.t_state) * 40)
        for i, line in enumerate(lines):
            c.center(y + i, line[:max(0, budget)].ljust(len(line)), col)
            budget -= len(line) + 8  # a short pause between lines
        self.typed_all = budget >= 0
        return self.typed_all

    def fmt(self, text):
        return text.format(word=self.word)

    def draw_key(self, c, x, y, now):
        """Key lamp, what you've keyed so far, its letter, and the letter lock-in bar."""
        k = self.keyer
        lit = k.sounding() or (k.ev and now - k.last < .12)
        label = self.text('key')
        c.put(x, y, label, INK if lit else DIM, LAMP if lit else FAINT)
        x += len(label) + 2
        live = k.live(now)
        c.put(x, y, pretty(live), LAMP)
        if live:
            c.put(x + 16, y, f'= {DECODE.get(live, "?")}', DIM if k.ev else PAPER)
        if k.pattern and not k.ev:
            n = min(5, int((now - k.last) / k.letter_gap * 5))
            c.put(x + 21, y, '▮' * n + '▯' * (5 - n), TEAL)

    def draw_hud(self, c):
        c.band(0, 1, BAND)
        c.put(1, 0, self.text('score', score=self.score), AMBER)
        c.put(22, 0, self.text('chapter_hud', n=self.chapter, total=len(self.chapters)), AMBER)
        c.put(44, 0, '♥ ' * self.lives, ALERT)
        best = self.text('best', best=max(self.hi, self.score))
        c.put(79 - len(best), 0, best, DIM)

    def draw_header(self, c, line2):
        c.band(1, 2, SEND_BAND if self.mode == 'encode' else LISTEN_BAND)
        c.put(1, 1, self.text('send' if self.mode == 'encode' else 'receive') + self.beat['title'], PAPER)
        message = self.text('message', n=self.beat_no + 1)
        c.put(79 - len(message), 1, message, AMBER)
        c.put(1, 2, line2, TEAL)

    def draw_scene(self, c, now, key, p, won_t=None, lost_t=None):
        mover, target, sky, ground = SCENES[key]
        c.band(3, 11, EMBER if lost_t is not None else sky)
        c.band(11, 13, ground)
        rnd = random.Random(key)
        for _ in range(16):
            x, y, phase = rnd.randrange(80), rnd.randrange(3, 9), rnd.random()
            c.put(x, y, '·', PAPER if (now * .3 + phase) % 1 > .2 else FAINT)
        if sky == FOG:
            for i in range(10):
                x = int(rnd.random() * 80 + now * .8) % 80
                c.put(x, 4 + i % 6, '░' * rnd.randrange(4, 12), DIM)
        tgt, mov = SPRITES[target], SPRITES[mover]
        tw, th = len(tgt[0]), (len(tgt) + 1) // 2
        mw, mh = len(mov[0]), (len(mov) + 1) // 2
        tx, ty = 76 - tw, 11 - th
        mx = 2 + int(p * (tx - mw - 3))
        my = 4 if mover in FLYERS else 11 - mh
        if mover == 'spark' and won_t is None:
            c.put(mx + 2, my, '━' * (tx - mx), DIM)
        sprite(c, tx, ty, tgt)
        if lost_t is not None:
            for i in range(14):
                r = random.Random(i)
                rise = (lost_t * 1.2 + r.random() * 5) % 5
                y = ty + th - 1 - int(rise)
                if y >= 3:
                    c.put(tx + r.randrange(tw), y, '░▒'[i % 2], DIM if rise < 2.5 else FAINT)
            for x in range(tx, tx + tw):
                if (x * 7 + int(now * 3)) % 4 == 0:
                    c.put(x, ty, '▲', AMBER if (x + int(now * 2)) % 2 else ALERT)
        if won_t is None:
            sprite(c, mx, my, mov, flicker=int(now * 4) % 2)
        elif won_t < 1.5:
            sprite(c, mx, my, mov, faded=True)

    def draw_title(self, c, now):
        self.draw_scene(c, now, 'wireless', (now / 120) % 1)
        big_center(c, 14, self.text('title_big'), AMBER)
        c.center(19, self.text('subtitle'), TEAL)
        c.center(20, self.text('tap_hold', dot=DOT, dah=DAH), PAPER)
        menu = self.text('menu_begin')
        if self.saved_chapter > 1:
            menu += '   ' + self.text('menu_continue', n=self.saved_chapter)
        c.center(22, menu, AMBER)
        c.center(23, self.text('menu_rest'), AMBER)
        if self.hi:
            c.center(1, self.text('best', best=self.hi), FAINT)

    def draw_chapter(self, c, now):
        chap = self.chapters[self.chapter - 1]
        self.draw_hud(c)
        c.center(2, self.text('chapter_label', n=self.chapter), DIM)
        big_center(c, 3, chap['title'], AMBER)
        self.typewriter(c, 8, chap['intro'], now)
        c.center(12, self.text('first_letters' if self.chapter == 1 else 'new_letters'), TEAL)
        col_w = 76 // len(self.new_letters)
        last = self.free_text.rstrip()[-1:]
        for i, ch in enumerate(self.new_letters):
            x = 2 + i * col_w + col_w // 2 - 9
            big(c, x, 14, ch, GO if last == ch else PAPER)
            c.put(x + 8, 15, pretty(MORSE[ch]), LAMP)
        c.put(10, 19, self.text('try_them') + self.free_text[-50:], DIM)
        self.draw_key(c, 24, 20, now)
        if self.typed_all and int(now * 1.5) % 2:
            c.center(22, self.text('enter_begin'), AMBER)
        c.center(23, self.text('chapter_help'), FAINT)

    def draw_brief(self, c, now):
        self.draw_hud(c)
        self.draw_header(c, self.text('brief_line', n=self.chapter, title=self.chapters[self.chapter - 1]['title']))
        self.draw_scene(c, now, self.beat['scene'], 0)
        if self.typewriter(c, 14, self.beat['brief'] + ['', self.beat['task']], now):
            if self.mode == 'encode':
                c.center(19, self.text('code_word', word=self.word), AMBER)
            if int(now * 1.5) % 2:
                c.center(22, self.text('ready'), AMBER)

    def draw_play(self, c, now):
        self.draw_hud(c)
        self.draw_header(c, self.beat['task'])
        self.draw_scene(c, now, self.beat['scene'], self.progress(now))
        left = max(0.0, self.t_end - now)
        frac = left / self.t_total
        col = DIM if frac > .3 else (ALERT if frac > .15 or int(now * 2) % 2 else EMBER)
        n = int(frac * 60)
        c.put(7, 13, '▬' * n, col)
        c.put(7 + n, 13, '▬' * (60 - n), BAND)
        c.put(70, 13, f'{left:4.0f}s', col)
        x0 = 40 - bigw(self.word) // 2
        for i, ch in enumerate(self.word):
            done = i < self.pos
            col = GO if done else LAMP if i == self.pos else FAINT
            big(c, x0 + i * 6, 15, ch if self.mode == 'encode' or done else '_', col)
        if self.mode == 'encode':
            if self.hint and self.pos < len(self.word):
                hint = pretty(MORSE[self.word[self.pos]])
                c.put(x0 + self.pos * 6 + 2 - len(hint) // 2, 19, hint, TEAL)
            self.draw_key(c, 24, 20, now)
            help_ = self.text('encode_help')
        else:
            t = now - self.sig_t0
            if self.radio_only:
                c.center(20, self.text('no_lamp'), DIM)
            else:
                lit = any(s <= t < e for s, e, _, _ in self.on)
                c.put(2, 20, self.text('lamp'), INK if lit else DIM, LAMP if lit else FAINT)
                letters = {}
                for s, _, e, li in self.on:
                    if s <= t:
                        letters.setdefault(li, []).append(e)
                tape = '   '.join(pretty(''.join(v)) for v in letters.values())
                c.put(10, 20, tape[-68:], TEAL)
            help_ = self.text('decode_help')
        if now < self.msg_until:
            c.center(21, self.msg, self.msg_col)
        c.center(23, help_, FAINT)

    def draw_result(self, c, now, won):
        t = now - self.t_state
        self.draw_hud(c)
        self.draw_header(c, self.beat['task'])
        if won:
            self.draw_scene(c, now, self.beat['scene'], self.p_end, won_t=t)
            big_center(c, 14, self.banner, GO)
            c.center(20, self.fmt(self.beat['win']), PAPER)
            c.center(21, self.text('time_bonus', bonus=self.bonus), AMBER)
        else:
            self.draw_scene(c, now, self.beat['scene'], self.p_end, lost_t=t)
            big_center(c, 14, self.banner, ALERT)
            c.center(20, self.fmt(self.beat['lose']), PAPER)
            c.center(21, self.text('lives_left', n=self.lives) if self.lives else self.text('no_lives'), ALERT)
        c.center(19, f'{self.word}  =  ' + '   '.join(pretty(MORSE[ch]) for ch in self.word), TEAL)
        if t > 1 and int(now * 1.5) % 2:
            c.center(23, self.text('continue'), AMBER)

    def draw_win(self, c, now):
        self.draw_result(c, now, True)

    def draw_lose(self, c, now):
        self.draw_result(c, now, False)

    def draw_free(self, c, now):
        c.band(0, 1, BAND)
        c.center(0, self.text('practice'), AMBER)
        last = self.free_text.rstrip()[-1:]
        for i, ch in enumerate(MORSE):
            x, y = 3 + (i // 9) * 19, 2 + i % 9
            c.put(x, y, ch, LAMP if ch == last else PAPER)
            c.put(x + 2, y, pretty(MORSE[ch]), LAMP if ch == last else TEAL)
        big_center(c, 12, self.free_text[-12:], AMBER)
        c.center(17, self.free_text[-70:], DIM)
        self.draw_key(c, 24, 19, now)
        c.center(23, self.text('free_help'), FAINT)

    def draw_over(self, c, now):
        big_center(c, 5, self.text('over_big'), ALERT)
        c.center(11, self.text('over_line'), DIM)
        c.center(14, self.text('final_score', score=self.score), AMBER)
        if self.new_hi:
            c.center(15, self.text('new_best'), PAPER)
        c.center(17, self.text('over_continue', n=self.chapter), DIM)
        if now - self.t_state > 1.5 and int(now * 1.5) % 2:
            c.center(21, '[ENTER]', PAPER)

    def draw_ending(self, c, now):
        self.draw_scene(c, now, 'wireless', 1.0, won_t=9)
        big_center(c, 14, self.text('end_big'), AMBER)
        if self.typewriter(c, 19, ENDING[self.lang], now, DIM):
            line = self.text('final_score', score=self.score)
            c.center(23, line + ('  ·  ' + self.text('new_best') if self.new_hi else ''), AMBER)

    def draw_lang(self, c, now):
        self.draw_scene(c, now, 'wireless', (now / 120) % 1)
        big_center(c, 14, 'MORSE', AMBER)
        for i, (lang, name) in enumerate([('en', 'ENGLISH (EN-US)'), ('pt', 'PORTUGUÊS (PT-BR)')]):
            chosen = lang == self.lang
            c.center(19 + i, ('▸ ' if chosen else '  ') + f'[{i + 1}] {name}', LAMP if chosen else DIM)
        if int(now * 1.5) % 2:
            c.center(22, '[ENTER] OK', AMBER)


# --------------------------------------------------------------------- main

def gnome_key_repeat():
    """(delay, interval) in seconds from GNOME settings, else common defaults."""
    try:
        def get(key):
            out = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.peripherals.keyboard', key],
                                 capture_output=True, text=True, timeout=1).stdout
            return int(out.split()[-1]) / 1000
        return get('delay'), get('repeat-interval')
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return .5, .033


def selftest():
    def run(times):
        k = Keyer(.25, .045, .8)
        for t in times:
            k.press(t)
        return k.tick(times[-1] + 2)

    def hold(t, dur):
        return [t] + [t + .25 + i * .045 for i in range(int((dur - .25) / .045) + 1)]

    assert run([0]) == '.'
    assert run(hold(0, .6)) == '-'
    assert run([0, .2, .4]) == '...'
    assert run([0] + hold(.3, .7)) == '.-'
    assert run(hold(0, .5) + [.8]) == '-.'
    assert run(hold(0, .5) + hold(.8, .5)) == '--'
    k = PressKeyer(.2, .8)
    for down, up in [(0, .08), (.3, .7), (.9, .95)]:
        k.press(down)
        k.release(up)
    assert k.tick(2) == '.-.'
    assert DECODE['.-'] == 'A'
    assert all(len(g) == 7 and all(len(r) == 5 for r in g) for g in FONT.values())
    assert all(ch in FONT for ch in MORSE)
    assert all(len(set(map(len, rows))) == 1 and set(''.join(rows)) <= set(PAL) | {'.'}
               for rows in SPRITES.values())
    for lang in LANGS:
        chapters = CHAPTERS[lang]
        assert len(chapters) == len(LEVELS) and set(UI[lang]) == set(UI['en'])
        assert all(set(w) <= set(MORSE) for w in WORDS[lang])
        assert all(len(ch['beats']) == 3 and bigw(ch['title']) <= 80 for ch in chapters)
        assert all(bigw(b) <= 80 for b in WIN_BANNERS[lang] + LOSE_BANNERS[lang])
        lines = ENDING[lang] + [ln for ch in chapters for ln in ch['intro']]
        for b in (b for ch in chapters for b in ch['beats']):
            assert b['scene'] in SCENES
            lines += b['brief'] + [b['task'], b['win'].format(word='W' * 8), b['lose'].format(word='W' * 8)]
        assert all(len(ln) <= 78 for ln in lines), [ln for ln in lines if len(ln) > 78]
    print('selftest ok')


def main():
    delay, interval = gnome_key_repeat()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repeat-delay', type=float, default=delay, help='keyboard autorepeat delay, seconds')
    ap.add_argument('--repeat-interval', type=float, default=interval, help='autorepeat interval, seconds')
    ap.add_argument('--letter-gap', type=float, default=.3, help='silence that ends a letter, seconds')
    ap.add_argument('--volume', type=float, default=.4, help='0 (mute) to 1')
    ap.add_argument('--dah-time', type=float, default=.2,
                    help='with a real keyboard device: press at least this long for a dah, seconds')
    ap.add_argument('--no-evdev', action='store_true',
                    help="don't read /dev/input; detect holds from autorepeat instead")
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    kbd_fds = [] if args.no_evdev else open_keyboards()
    args.evdev = bool(kbd_fds)
    audio = Audio(args.volume)
    game = Game(args, audio)
    fd, out = sys.stdin.fileno(), sys.stdout
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        out.write('\x1b[?1049h\x1b[?25l\x1b[?7l')
        last = ''
        while True:
            ready, _, _ = select.select([fd] + kbd_fds, [], [], 1 / 30)
            now = time.monotonic()
            for kfd in kbd_fds:
                if kfd in ready:
                    for down in read_space_events(kfd):
                        game.device_space(down, now)
            if fd in ready:
                data = os.read(fd, 64).decode(errors='ignore')
                keys = (['ESC'] if data == '\x1b' else []) if data.startswith('\x1b') else list(data)
                for k in keys:
                    game.key(k, now)
            game.tick(now)
            frame = game.draw(now).render()
            if frame != last:
                out.write(frame)
                out.flush()
                last = frame
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        out.write('\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l')
        out.flush()
        audio.close()


if __name__ == '__main__':
    main()
