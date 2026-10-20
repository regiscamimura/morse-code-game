#!/usr/bin/env python3
"""MORSE CODE - Station Seven, 1936. A Morse code story for the terminal.

TAP space = dit (•)    HOLD space = dah (━)

The space bar's real press and release come from the Windows console, the
Kitty keyboard protocol (Ghostty, Kitty, WezTerm, iTerm2...) or /dev/input on
Linux; a press of --dah-time or longer is a dah. Elsewhere terminals send no
key-release events, so a hold is recognised from the keyboard's autorepeat
burst; tune --repeat-delay / --repeat-interval then.
"""
import argparse
import itertools
import json
import math
import os
import random
import re
import select
import struct
import subprocess
import sys
import threading
import time
import unicodedata

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    import ctypes
    from ctypes import wintypes
else:
    import fcntl
    import termios
    import tty

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
    dict(title='CARCARÁ', intro=[
        'HALE EXPLICA NUMA CARTA LACRADA, ENTREGUE EM MÃOS.',
        'CARCARÁ: UMA REDE QUE VENDE SEGREDOS NAVAIS A QUEM PAGAR MAIS.',
        'ELES FALAM À NOITE, E FALAM EM MORSE.'], beats=[
        beat('decode', 'O ENCONTRO', [
            'TRÁFEGO DO CARCARÁ NA FAIXA NOTURNA.',
            'UM LUGAR ESTÁ SENDO MENCIONADO.'],
            'DECIFRE O LOCAL DO ENCONTRO.',
            'O ENCONTRO É EM {word}. HALE MANDA HOMENS VIGIAREM.',
            'A MENSAGEM TERMINA. NINGUÉM VIGIA O ENCONTRO.', 'wireless'),
        beat('encode', 'O TREM NOTURNO', [
            'UM MENSAGEIRO COM PAPÉIS DO ALMIRANTADO ESTÁ NO TREM NOTURNO.',
            'HOMENS DO CARCARÁ EMBARCARAM NA ÚLTIMA PARADA.'],
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
            "O BILHETE DIZ {word}. ASSINADO: 'S'.",
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
            'UM ARTEFATO DO CARCARÁ, COM UM MANIPULADOR TELEGRÁFICO COMO TRAVA.'],
            'BATA O CÓDIGO QUE O DESLIGA.',
            'O TIQUE-TAQUE PARA.',
            'A PRAIA SE ILUMINA POR UM INSTANTE. DEPOIS, ESCURIDÃO.', 'bomb'),
    ]),
    dict(title='SABIÁ', intro=[
        "O BILHETE ESTAVA ASSINADO 'S'.",
        'HALE ENFIM ADMITE: SABIÁ NOS PASSA INFORMAÇÕES DE DENTRO DO CARCARÁ.',
        'SABIÁ SÓ FALA COM VOCÊ.'], beats=[
        beat('encode', 'RECONHECIMENTO', [
            'SABIÁ SÓ RESPONDE À PALAVRA DE RECONHECIMENTO CERTA.',
            'UM CARRO DE PATRULHA DO CARCARÁ JÁ ESTÁ NA ESTRADA DA COSTA.'],
            'ENVIE A PALAVRA DE RECONHECIMENTO.',
            'UMA PAUSA. DEPOIS, DOIS PONTOS. SABIÁ ESTÁ OUVINDO.',
            'NENHUMA RESPOSTA. SABIÁ FICA EM SILÊNCIO.', 'road'),
        beat('decode', 'O QUE FOI LEVADO', [
            'SABIÁ TRANSMITE DEPRESSA, COM A MÃO TRÊMULA.',
            'O CARCARÁ LEVOU ALGO DE UM ARSENAL DA MARINHA.'],
            'DECIFRE O QUE FOI LEVADO.',
            "SABIÁ: '{word}. E A NOVA MÁQUINA DE CIFRA.'",
            'SABIÁ PARA NO MEIO DA FRASE.', 'wireless'),
        beat('decode', 'A ROTA', [
            'A MÁQUINA SERÁ VENDIDA NO EXTERIOR.',
            'SABIÁ CONHECE A ROTA.'],
            'DECIFRE A ROTA.',
            'ELA SAI POR {word}. O CERCO SE FECHA.',
            'ESTÁTICA. SABIÁ SUMIU POR ESTA NOITE.', 'wireless'),
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
        'SABIÁ MANDA UMA LINHA EM PLENO DIA, CONTRA TODAS AS REGRAS:',
        "'ELES SABEM.'",
        'DEPOIS, NADA.'], beats=[
        beat('decode', 'ESCONDERIJO', [
            'HORAS DEPOIS. UM SINAL FRACO VINDO DO INTERIOR.',
            'SABIÁ SE ESCONDEU E ESTÁ MANDANDO O ENDEREÇO.'],
            'DECIFRE O ESCONDERIJO.',
            'SABIÁ ESTÁ EM {word}. AGUENTE FIRME, SABIÁ.',
            'O SINAL CAI.', 'wireless'),
        beat('encode', 'RESGATE', [
            'UM CARRO DO CARCARÁ JÁ ESTÁ A CAMINHO DO ESCONDERIJO.',
            'NOSSO MOTORISTA SÓ ESPERA A PALAVRA.'],
            'ENVIE A PALAVRA.',
            'FARÓIS NA ESTRADINHA. SABIÁ JÁ ESTÁ LONGE DALI.',
            'O CARRO DO CARCARÁ CHEGA PRIMEIRO.', 'road'),
        beat('decode', 'O AVISO DE SABIÁ', [
            'DO BANCO DE TRÁS, SABIÁ BATE UMA PALAVRA NUM RÁDIO PORTÁTIL.',
            'O CODINOME DE QUEM COMANDA O CARCARÁ.'],
            'DECIFRE O CODINOME.',
            'QUEM COMANDA O CARCARÁ É {word}. ALGUÉM DE DENTRO.',
            'O CARRO SAI DO ALCANCE.', 'road'),
    ]),
    dict(title='A BATIDA', intro=[
        'TODO TELEGRAFISTA TEM UMA BATIDA: UM RITMO TÃO PESSOAL QUANTO A LETRA.',
        'O CARCARÁ SEMPRE SOUBE O QUE O ALMIRANTADO SABIA.',
        'VOCÊ COMEÇA A OUVIR GRAVAÇÕES ANTIGAS.'], beats=[
        beat('decode', 'OS CILINDROS', [
            'CILINDROS DE CERA COM O TRÁFEGO DO ALMIRANTADO DO MÊS PASSADO.',
            'POR BAIXO DAS MENSAGENS DE ROTINA, UMA SEGUNDA MÃO TRANSMITE.'],
            'DECIFRE A TRANSMISSÃO ESCONDIDA.',
            'DIZ {word}. VOCÊ CONHECE ESSA BATIDA. É HALE.',
            'O CILINDRO RACHA.', 'wireless'),
        beat('encode', 'NÃO CONFIE EM NINGUÉM', [
            'HALE CONTROLA AS LINHAS DO ALMIRANTADO.',
            'SÓ SE PODE CONFIAR EM SABIÁ AGORA.'],
            'ENVIE A PALAVRA DE ALERTA A SABIÁ.',
            "SABIÁ RESPONDE: 'ENTENDIDO. NÃO CONFIE EM NINGUÉM.'",
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
        'UM AVIÃO DO CARCARÁ ESTÁ VINDO PARA O POSTO.',
        'O CAMPO DE POUSO AINDA PODE OUVIR UM CHAMADO HONESTO.'], beats=[
        beat('encode', 'PEDIDO DE SOCORRO', [
            'O AVIÃO JÁ ESTÁ SOBRE O MAR.',
            'O CAMPO DE POUSO É SUA ÚNICA CHANCE.'],
            'ENVIE O PEDIDO DE SOCORRO.',
            'DOIS BIPLANOS SOBEM PARA ENFRENTÁ-LO. O INTRUSO RECUA.',
            'NINGUÉM RESPONDE.', 'air'),
        beat('decode', 'O PILOTO', [
            'O CARCARÁ BLOQUEIA A FAIXA. UM DOS PILOTOS AINDA CONSEGUE PASSAR.',
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
            'SABIÁ TEM O DIAGRAMA.',
            'SABIÁ TRANSMITE O PRIMEIRO PASSO, DEVAGAR.'],
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
            'A MENSAGEM CHEGA A TODAS AS ESTAÇÕES. O CARCARÁ ACABOU.',
            'O TRANSMISSOR FALHA. ENVIE DE NOVO.', 'wireless'),
    ]),
]
ENDING_PT = [
    'AMANHECE NA COSTA. O TEMPORAL PASSOU.',
    'SABIÁ ENVIA UM ÚLTIMO SINAL: PONTO PONTO PONTO TRAÇO PONTO TRAÇO.',
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
    """Two queued channels (fx, sig) plus the player's sidetone.

    Played through PortAudio (the sounddevice package) where it's available,
    else streamed to aplay on Linux, else the game is silent.
    """

    OUT_RATE = RATE * 4  # sound cards rarely accept 11025 Hz; each sample is played 4 times

    def __init__(self, volume):
        self.volume = volume
        self.lock = threading.Lock()
        self.queues = {'fx': [], 'sig': []}
        self.key_on, self.blip, self.phase = False, 0, 0.0
        self.proc = None
        self.stream = self._open_portaudio()
        if self.stream or WINDOWS:
            return
        try:
            self.proc = subprocess.Popen(
                ['aplay', '-q', '-t', 'raw', '-f', 'U8', '-r', str(RATE), '-c', '1',
                 '--buffer-time=30000', '--period-time=7500'],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                env={**os.environ, 'PIPEWIRE_LATENCY': f'128/{RATE}'})
        except OSError:
            return  # no aplay either: play silently
        threading.Thread(target=self._stream_to_aplay, daemon=True).start()

    def _open_portaudio(self):
        try:
            import sounddevice
        except (ImportError, OSError):  # not installed, or no PortAudio library on this system
            return None
        try:
            stream = sounddevice.RawOutputStream(samplerate=self.OUT_RATE, channels=1, dtype='uint8',
                                                 latency='low', callback=self._fill_portaudio)
            stream.start()
            return stream
        except sounddevice.PortAudioError:
            return None

    def _fill_portaudio(self, outdata, frames, time_info, status):
        samples = self._render_audio(-(-frames // 4))
        out = bytearray(len(samples) * 4)
        for i in range(4):
            out[i::4] = samples
        outdata[:] = bytes(out[:frames])

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

    def _render_audio(self, sample_count):
        """The next `sample_count` 8-bit samples at RATE: both channels plus the sidetone."""
        buf = bytearray(sample_count)
        with self.lock:
            for i in range(sample_count):
                v = self._next_sample(self.queues['fx']) + self._next_sample(self.queues['sig'])
                if self.key_on or self.blip > 0:
                    self.blip -= 1
                    self.phase = (self.phase + KEY_HZ / RATE) % 1
                    v += .25 if self.phase < .5 else -.25
                buf[i] = max(0, min(255, int(128 + v * 100 * self.volume)))
        return buf

    def _stream_to_aplay(self):
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
            try:
                os.write(fd, self._render_audio(64))
            except OSError:
                return

    def close(self):
        if self.stream:
            self.stream.close()
        if self.proc:
            self.proc.kill()


# --------------------------------------------------------------------- terminal

SETUP_SCREEN = '\x1b[?1049h\x1b[?25l\x1b[?7l'
RESTORE_SCREEN = '\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l'
# Kitty keyboard protocol flags: 1 disambiguate + 2 report press/release + 8 every key as a code
KITTY_PUSH, KITTY_POP = '\x1b[>11u', '\x1b[<u'
KITTY_KEY = re.compile(r'\x1b\[(\d+)(?::\d*)*(?:;(\d*)(?::(\d+))?)?(?:;[\d:]*)?u')
INPUT_TOKEN = re.compile(r'\x1b\[[0-9:;?<=>]*[ -/]*[@-~]|\x1bO.|\x1b|.', re.S)
KITTY_NAMED = {13: '\n', 9: '\t', 127: '\x7f', 8: '\x7f', 27: 'ESC'}
KITTY_PRESS, KITTY_REPEAT, KITTY_RELEASE, KITTY_CTRL = 1, 2, 3, 4


class UnixTerminal:
    """cbreak tty. Space releases come from the Kitty keyboard protocol when the
    terminal speaks it, else from /dev/input on Linux, else they're unknown.

    read() returns events: ('space', True/False) for a real press/release, or
    ('key', k) for anything typed (k == ' ' only when releases are unknown).
    """

    def __init__(self, use_devices):
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.kitty = self._terminal_reports_releases()
        if self.kitty:
            self.write(KITTY_PUSH)
        on_linux = sys.platform.startswith('linux')
        self.devices = open_keyboards() if use_devices and on_linux and not self.kitty else []
        self.device_seen = False
        self.write(SETUP_SCREEN)

    @property
    def reports_release(self):
        return self.kitty or bool(self.devices)

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def _terminal_reports_releases(self):
        # Ask for the Kitty keyboard flags, then for the device attributes every
        # terminal answers. A flags reply arriving first means the protocol works.
        self.write('\x1b[?u\x1b[c')
        reply, deadline = '', time.monotonic() + .5
        while not re.search(r'\x1b\[\?[\d;]*c', reply) and time.monotonic() < deadline:
            if select.select([self.fd], [], [], .05)[0]:
                reply += os.read(self.fd, 256).decode(errors='ignore')
        return bool(re.search(r'\x1b\[\?\d+u', reply))

    def read(self, timeout):
        events = []
        ready = select.select([self.fd] + self.devices, [], [], timeout)[0]
        for device in self.devices:
            if device in ready:
                for down in read_space_events(device):
                    self.device_seen = True
                    events.append(('space', down))
        if self.fd in ready:
            for token in INPUT_TOKEN.findall(os.read(self.fd, 256).decode(errors='ignore')):
                events += self._decode_token(token)
        return events

    def _decode_token(self, token):
        match = KITTY_KEY.fullmatch(token)
        if match:
            code, mods, kind = int(match[1]), int(match[2] or 1) - 1, int(match[3] or KITTY_PRESS)
            if code == 32:
                return [] if kind == KITTY_REPEAT else [('space', kind == KITTY_PRESS)]
            if kind == KITTY_RELEASE:
                return []
            if mods & KITTY_CTRL and code == ord('c'):
                raise KeyboardInterrupt
            if code in KITTY_NAMED:
                return [('key', KITTY_NAMED[code])]
            return [('key', chr(code))] if 32 < code < 0xE000 else []  # skip modifier-only keys
        if token == '\x1b':
            return [('key', 'ESC')]
        if token.startswith('\x1b'):
            return []
        if token == ' ' and self.devices:
            if self.device_seen:
                return []  # the devices already reported this press
            # the terminal saw a space the devices didn't: they aren't this keyboard
            for device in self.devices:
                os.close(device)
            self.devices = []
        return [('key', token)]

    def restore(self):
        if self.kitty:
            self.write(KITTY_POP)
        self.write(RESTORE_SCREEN)
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        for device in self.devices:
            os.close(device)


if WINDOWS:
    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [('bKeyDown', wintypes.BOOL), ('wRepeatCount', wintypes.WORD),
                    ('wVirtualKeyCode', wintypes.WORD), ('wVirtualScanCode', wintypes.WORD),
                    ('uChar', wintypes.WCHAR), ('dwControlKeyState', wintypes.DWORD)]

    class INPUT_RECORD(ctypes.Structure):
        # the real Event is a union; the key record is its largest member
        _fields_ = [('EventType', wintypes.WORD), ('Event', KEY_EVENT_RECORD)]


class WindowsConsole:
    """Windows console input records carry real key-down and key-up events.

    read() returns the same events as UnixTerminal.read().
    """

    reports_release = True
    KEY_EVENT, VK_SPACE, VK_ESCAPE, VK_C, CTRL_PRESSED = 1, 0x20, 0x1B, 0x43, 0x0C
    INPUT_RAW = 0x0080  # extended flags only: no line input, echo, quick-edit or Ctrl+C handling
    OUTPUT_ANSI = 0x0001 | 0x0004  # processed output + virtual terminal sequences

    def __init__(self):
        self.kernel = ctypes.windll.kernel32
        self.kernel.GetStdHandle.restype = wintypes.HANDLE
        self.stdin, self.stdout = self.kernel.GetStdHandle(-10), self.kernel.GetStdHandle(-11)
        self.saved_in, self.saved_out = wintypes.DWORD(), wintypes.DWORD()
        self.kernel.GetConsoleMode(self.stdin, ctypes.byref(self.saved_in))
        self.kernel.GetConsoleMode(self.stdout, ctypes.byref(self.saved_out))
        self.kernel.SetConsoleMode(self.stdin, self.INPUT_RAW)
        self.kernel.SetConsoleMode(self.stdout, self.saved_out.value | self.OUTPUT_ANSI)
        self.kernel.SetConsoleOutputCP(65001)
        sys.stdout.reconfigure(encoding='utf-8')
        self.space_down = False
        self.write(SETUP_SCREEN)

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def read(self, timeout):
        events = []
        if self.kernel.WaitForSingleObject(self.stdin, int(timeout * 1000)) != 0:
            return events
        count = wintypes.DWORD()
        self.kernel.GetNumberOfConsoleInputEvents(self.stdin, ctypes.byref(count))
        if not count.value:
            return events
        records = (INPUT_RECORD * count.value)()
        self.kernel.ReadConsoleInputW(self.stdin, records, count.value, ctypes.byref(count))
        for record in records[:count.value]:
            if record.EventType != self.KEY_EVENT:
                continue
            key = record.Event
            if key.wVirtualKeyCode == self.VK_SPACE:
                if bool(key.bKeyDown) != self.space_down:  # held keys repeat their key-down
                    self.space_down = bool(key.bKeyDown)
                    events.append(('space', self.space_down))
            elif not key.bKeyDown:
                continue
            elif key.wVirtualKeyCode == self.VK_ESCAPE:
                events.append(('key', 'ESC'))
            elif key.wVirtualKeyCode == self.VK_C and key.dwControlKeyState & self.CTRL_PRESSED:
                raise KeyboardInterrupt
            elif key.uChar not in ('', '\x00'):  # keys that type nothing carry NUL
                events.append(('key', {'\r': '\n', '\x08': '\x7f'}.get(key.uChar, key.uChar)))
        return events

    def restore(self):
        self.write(RESTORE_SCREEN)
        self.kernel.SetConsoleMode(self.stdin, self.saved_in.value)
        self.kernel.SetConsoleMode(self.stdout, self.saved_out.value)


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

def save_file_path():
    """Per-user data file: a one-file build unpacks itself into a temporary folder."""
    if WINDOWS:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'morse-code', 'save.json')


def load_save(path):
    # .save.json beside the script is where saves lived before they moved to `path`
    beside_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.save.json')
    for candidate in (path, beside_script):
        try:
            with open(candidate) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


class Game:
    def __init__(self, args, audio, releases):
        self.args, self.audio, self.releases = args, audio, releases
        self.save_path = save_file_path()
        saved = load_save(self.save_path)
        self.hi, self.saved_chapter = saved.get('hi', 0), saved.get('chapter', 1)
        self.lang = saved.get('lang') if saved.get('lang') in LANGS else 'en'
        self.score = self.lives = self.combo = self.beat_no = 0
        self.chapter, self.mode, self.free_text, self.last_word = 1, 'encode', '', None
        self.msg_until = 0.0
        self.set_state('lang', time.monotonic())

    def write_save(self):
        try:
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
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
        self.keyer = self.new_keyer()
        self.audio.key_on = False

    def new_keyer(self):
        a = self.args
        if self.releases:
            return PressKeyer(a.dah_time, a.letter_gap)
        return Keyer(a.repeat_delay, a.repeat_interval, a.letter_gap)

    def use_release_keys(self, releases):
        """Switch between timing real presses and guessing holds from autorepeat."""
        self.releases = releases
        self.keyer = self.new_keyer()

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

    def key(self, k, now):
        s = self.state
        if k == 'ESC':
            if s in ('title', 'lang'):
                raise SystemExit
            return self.to_title(now)
        if k == ' ':  # a typed space: only sent when releases are unknown
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

def read_system_key_repeat():
    """(delay, interval) in seconds from macOS or GNOME settings, else common defaults."""
    def run(*command):
        return subprocess.run(command, capture_output=True, text=True, timeout=1).stdout

    try:
        if sys.platform == 'darwin':  # macOS stores both in units of 15 ms
            return (int(run('defaults', 'read', '-g', 'InitialKeyRepeat')) * .015,
                    int(run('defaults', 'read', '-g', 'KeyRepeat')) * .015)
        gnome = 'org.gnome.desktop.peripherals.keyboard'
        return (int(run('gsettings', 'get', gnome, 'delay').split()[-1]) / 1000,
                int(run('gsettings', 'get', gnome, 'repeat-interval').split()[-1]) / 1000)
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
    kitty = UnixTerminal.__new__(UnixTerminal)
    kitty.devices = []
    assert kitty._decode_token('\x1b[32u') == [('space', True)]
    assert kitty._decode_token('\x1b[32;1:3u') == [('space', False)]
    assert kitty._decode_token('\x1b[32;1:2u') == []
    assert kitty._decode_token('\x1b[97;2u') == [('key', 'a')]
    assert kitty._decode_token('\x1b[13u') == [('key', '\n')]
    assert kitty._decode_token('\x1b[57441;2u') == []
    assert INPUT_TOKEN.findall('a\x1b[32;1:3ub') == ['a', '\x1b[32;1:3u', 'b']
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
    delay, interval = read_system_key_repeat()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repeat-delay', type=float, default=delay, help='keyboard autorepeat delay, seconds')
    ap.add_argument('--repeat-interval', type=float, default=interval, help='autorepeat interval, seconds')
    ap.add_argument('--letter-gap', type=float, default=.3, help='silence that ends a letter, seconds')
    ap.add_argument('--volume', type=float, default=.4, help='0 (mute) to 1')
    ap.add_argument('--dah-time', type=float, default=.2,
                    help='with a real keyboard device: press at least this long for a dah, seconds')
    ap.add_argument('--no-evdev', action='store_true',
                    help="Linux: don't read /dev/input when the terminal can't report releases")
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    audio = Audio(args.volume)
    terminal = WindowsConsole() if WINDOWS else UnixTerminal(use_devices=not args.no_evdev)
    game = Game(args, audio, terminal.reports_release)
    try:
        last = ''
        while True:
            events = terminal.read(1 / 30)
            now = time.monotonic()
            if terminal.reports_release != game.releases:  # /dev/input turned out not to be ours
                game.use_release_keys(terminal.reports_release)
            for kind, value in events:
                if kind == 'space':
                    game.space_down(now) if value else game.space_up(now)
                else:
                    game.key(value, now)
            game.tick(now)
            frame = game.draw(now).render()
            if frame != last:
                terminal.write(frame)
                last = frame
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        terminal.restore()
        audio.close()


if __name__ == '__main__':
    main()
