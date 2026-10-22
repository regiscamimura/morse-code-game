#!/usr/bin/env python3
"""MORSE CODE - The Listener, 1912-1944. A Morse code story for the terminal.

TAP space = dit (•)    HOLD space = dah (━)

A press of --dah-time or longer is a dah when the terminal reports key releases
(see engine.py). Otherwise a hold is recognised from the keyboard's autorepeat
burst; tune --repeat-delay / --repeat-interval then.
"""
import argparse
import itertools
import os
import random
import time

from engine import (FONT, RATE, Audio, Canvas, Eject, add_arguments, big, big_center, big_text_width,
                    load_save, noise, notes, open_terminal, read_system_key_repeat, rest, run,
                    save_file_path, slide, sprite, square, draw_typed_lines, user_data_dir, write_save)
import engine

MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.', 'H': '....',
    'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 'P': '.--.',
    'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
}
DECODE = {v: k for k, v in MORSE.items()}
DOT, DAH = '•', '━'

# Koch-style unlock order: chapter N adds LEVELS[N-1]. '' is a review chapter: no new letters,
# drilling the two groups learned just before it.
LEVELS = ['ETAN', 'IM', 'SO', '', 'RK', 'DU', '', 'GW', 'HV', '', 'FL', 'BC', '', 'PJ', 'XY', '', 'ZQ']
# Receiving aids come off in steps, each on a review chapter so the letters are already familiar:
# lamp and scrolling tape, then the lamp alone, then sound only.
LAMP_ONLY_FROM, SOUND_ONLY_FROM = 7, 10

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
PALETTE = {'K': INK, 'D': FAINT, 'S': DIM, 'A': AMBER, 'O': FLAME, 'W': PAPER, 'Y': LAMP,
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
    'iceberg': ['.....W......', '....WWW.....', '...WWTWW....', '..WWWTWW.W..',
                '.WWWTTWWWWW.', '.WWTTTWWWWWW', 'WWWTTTTWWWWW', 'TTTTTTTTTTTT'],
}
FLYERS = {'airship', 'biplane'}

# scene: (mover, target, sky, ground). The mover creeping toward the target is the timer.
SCENES = {
    'wireless': ('airship', 'station', NIGHT, EARTH),
    'rail': ('train', 'city', NIGHT, EARTH),
    'harbour': ('submarine', 'liner', NIGHT, SEA),
    'fog': ('liner', 'lighthouse', FOG, SEA),
    'sea': ('liner', 'lighthouse', NIGHT, SEA),
    'ice': ('liner', 'iceberg', NIGHT, SEA),
    'bomb': ('spark', 'bomb', NIGHT, EARTH),
    'road': ('car', 'station', NIGHT, EARTH),
    'air': ('biplane', 'station', NIGHT, EARTH),
}


def new_mission(mode, title, brief, task, win, lose, scene, echo=False, word=None):
    """One mission. echo=True reuses the word decoded in the previous mission; word fixes it outright."""
    return dict(mode=mode, title=title, brief=brief, task=task, win=win, lose=lose, scene=scene, echo=echo,
                word=word)


CHAPTERS_EN = [
    dict(title='RADIO ROOM', intro=[
        'APRIL 1912. RMS CARPATHIA, NEW YORK TO FIUME.',
        'NIGHT OPERATOR. THE CREW CALLS YOU CORUJA: THE OWL. IT STICKS.',
        'PASSENGERS PAY BY THE WORD TO TELL THE WORLD THEY ARE AT SEA.',
        'TO SAVE MONEY THEY USE THE CODE BOOK: ONE WORD FOR A WHOLE SENTENCE.'], beats=[
        new_mission('encode', 'THE FIRST WIRE', [
            'MRS PEABODY OF OHIO WANTS HER SISTER TO KNOW THE SOUP WAS COLD.',
            "IN THE CODE BOOK THAT IS '{word}'. SIXPENCE, PAID IN ADVANCE."],
            'SEND THE CODE WORD TO CAPE RACE.',
            'CAPE RACE ACKNOWLEDGES. MRS PEABODY TIPS YOU A PENNY.',
            'CAPE RACE FADES. MRS PEABODY COMPLAINS TO THE PURSER.', 'sea'),
        new_mission('decode', 'THE NEWS', [
            '2300. CAPE RACE SENDS THE NIGHTLY NEWS.',
            'CAPTAIN ROSTRON LIKES THE BASEBALL SCORES WITH HIS COCOA.'],
            'COPY THE CODE WORD.',
            "'{word}'. THE CAPTAIN GRUNTS. IT WILL DO.",
            'THE NEWS SINKS INTO THE STATIC. THE COCOA GOES COLD.', 'sea'),
        new_mission('encode', 'A COMPLAINT', [
            'A GENTLEMAN IN FIRST CLASS IS SEASICK AND PESSIMISTIC.',
            "HIS BROKER MUST HAVE '{word}' AT ONCE. IT MEANS: SELL EVERYTHING."],
            'SEND IT BEFORE HE COMES BACK.',
            'SENT. THE GENTLEMAN GOES BACK TO BED. THE MARKET IS UNMOVED.',
            'HE COMES BACK. HE BRINGS HIS WIFE.', 'sea'),
    ]),
    dict(title='BUSY NIGHT', intro=[
        'THE BIG NEW SHIP IS ON THE AIR, OUTBOUND ON HER MAIDEN VOYAGE.',
        'TITANIC. CALL SIGN MGY. HER OPERATORS ARE BURIED IN PASSENGER TRAFFIC.',
        'EVERY MILLIONAIRE ABOARD WANTS TO WIRE HIS VALET.'], beats=[
        new_mission('decode', 'A RELAY', [
            'MGY ASKS YOU TO RELAY A MESSAGE THE SHORE CANNOT HEAR.',
            'FROM A MISS EVELYN MARSH, NINETEEN, TO HER AUNT IN SOUTHAMPTON.'],
            "COPY MISS MARSH'S CODE WORD.",
            "'{word}': THE DOG IS SEASICK. I AM NOT. BEST TRIP OF MY LIFE.",
            'THE RELAY FAILS. THE AUNT WILL NEVER HEAR ABOUT THE DOG.', 'sea'),
        new_mission('encode', 'PASS IT ON', [
            'THE AUNT MUST HAVE IT TONIGHT.',
            'PASS IT EAST TO THE NEXT STATION, EXACTLY AS YOU HEARD IT.'],
            "SEND MISS MARSH'S WORD ON.",
            'RECEIVED. IN SOUTHAMPTON, AN AUNT IS RELIEVED ABOUT A DOG.',
            'THE STATION DOES NOT ANSWER.', 'sea', echo=True),
        new_mission('decode', 'ICE', [
            'A STEAMER TO THE NORTH IS WARNING ANYONE WHO WILL LISTEN.',
            'MGY TELLS IT TO SHUT UP. MGY IS BUSY.'],
            'COPY THE ICE REPORT.',
            "'{word}'. YOU PIN IT ABOVE THE KEY. ICE, ALL ALONG HER ROUTE.",
            "THE WARNING IS LOST UNDER MGY'S PASSENGER CHATTER.", 'ice'),
    ]),
    dict(title='COME AT ONCE', intro=[
        '14 APRIL 1912. 2335. YOUR WATCH IS OVER. ONE BOOT IS ALREADY OFF.',
        'YOU KEEP THE HEADPHONES ON A MOMENT LONGER, TO PASS MGY SOME NEWS.',
        'MGY ANSWERS BEFORE YOU FINISH.'], beats=[
        new_mission('decode', 'DISTRESS', [
            'TITANIC: COME AT ONCE. WE HAVE STRUCK A BERG.',
            'THEN THE NEW CALL. NO OPERATOR HAS EVER HEARD IT IN EARNEST.'],
            'COPY THE CALL.',
            '{word}. YOU RUN TO THE BRIDGE IN ONE BOOT.',
            'IT MUST BE A JOKE. IT IS NOT. LISTEN AGAIN.', 'ice', word='SOS'),
        new_mission('encode', 'COMING HARD', [
            'CAPTAIN ROSTRON TURNS THE SHIP BEFORE HE IS DRESSED.',
            'FIFTY-EIGHT MILES. FOUR HOURS AT FULL STEAM, THROUGH ICE.'],
            'TELL THEM YOU ARE COMING.',
            "MGY: 'COME AS QUICK AS POSSIBLE, OLD MAN. ENGINE ROOM FILLING.'",
            'MGY KEEPS CALLING. THEY DO NOT KNOW ANYONE HEARD.', 'ice'),
        new_mission('decode', 'THE LAST WORD', [
            '0127. MGY IS FAINT NOW. HER POWER IS FAILING.',
            'ONE MORE WORD FROM THE DYING SHIP.'],
            'COPY IT.',
            '{word}. THEN STATIC. ONLY STATIC.',
            'THE STATIC TAKES IT. LISTEN. PLEASE.', 'ice'),
    ]),
    dict(title='NAMES', intro=[
        '0410. LIFEBOATS IN THE GREY LIGHT. NO SHIP. ONLY ICE AND WRECKAGE.',
        'THE CARPATHIA TAKES ON 705 SOULS. THE WORLD IS SCREAMING FOR NEWS.',
        'THE CAPTAIN ORDERS: SURVIVOR NAMES FIRST. NOTHING FOR THE PRESS.'], beats=[
        new_mission('encode', 'THE LIST', [
            'NAME AFTER NAME, THIRTY HOURS WITHOUT SLEEP.',
            "THE NEXT FAMILY ASKED FOR A CODE WORD: '{word}'. IT MEANS ALIVE."],
            'SEND IT.',
            'ACKNOWLEDGED. SOMEWHERE, A FAMILY STOPS WAITING.',
            'YOUR HAND CRAMPS. THE SHORE STATION LOSES YOU.', 'sea'),
        new_mission('decode', 'A NAME YOU KNOW', [
            'ON THE LIST: MARSH, E., MISS. ALIVE. SHE FINDS THE RADIO ROOM.',
            'SHE LEARNED MORSE WATCHING THE OPERATORS ON TITANIC.',
            'SHE TAPS HER MESSAGE ON YOUR DESK WITH A PENCIL.'],
            'READ WHAT SHE TAPS.',
            "'{word}'. SHE WANTS IT SENT TO THE AUNT. THE DOG DID NOT MAKE IT.",
            'SHE TAPS TOO FAST. SHE LAUGHS, FOR THE FIRST TIME IN TWO DAYS.', 'sea'),
        new_mission('encode', 'THE AUNT', [
            'THE SAME AUNT. THE SAME STATION. A DIFFERENT KIND OF MESSAGE.'],
            "SEND MISS MARSH'S WORD.",
            'THE AUNT ANSWERS IN FOUR MINUTES. MISS MARSH CRIES, AT LAST.',
            'THE LINE IS JAMMED WITH PRESS TRAFFIC.', 'sea', echo=True),
    ]),
    dict(title='ROOM 40', intro=[
        'AUGUST 1914. WAR.',
        'A MAN FROM THE ADMIRALTY KNOWS WHO KEPT THE CARPATHIA ON THE AIR.',
        'HE WANTS THAT EAR ON THE NORFOLK COAST, ON THE GERMAN FLEET.',
        'THE GROUPS YOU COPY GO TO A ROOM IN LONDON. ROOM 40.'], beats=[
        new_mission('decode', 'INTERCEPT', [
            'GERMAN NAVAL TRAFFIC. GROUPS OF LETTERS THAT MEAN NOTHING TO YOU.',
            'YOU ARE NOT TOLD WHAT THEY MEAN. YOU ARE TOLD NOT TO MISS ONE.'],
            'COPY THE GROUP.',
            '{word}. A DESPATCH RIDER TAKES IT TO LONDON. NO ONE SAYS THANKS.',
            'THE GROUP IS GONE. A CLERK IN LONDON HAS A HOLE IN HIS PAGE.', 'wireless'),
        new_mission('encode', 'THE LANDLINE', [
            'ROOM 40 WANTS EVERY GROUP WITHIN THE HOUR.',
            'THEY HAVE A CAPTURED GERMAN CODE BOOK. NO ONE TELLS YOU THAT.'],
            'PASS THE GROUP TO LONDON.',
            'LONDON ACKNOWLEDGES. SOMEONE OPENS A BOOK YOU WILL NEVER SEE.',
            'THE LINE IS BUSY. LONDON WAITS.', 'wireless', echo=True),
        new_mission('decode', 'THE RAID', [
            'DECEMBER. THE GERMAN SQUADRON IS AT SEA. THE TRAFFIC DOUBLES.',
            'A CARELESS OPERATOR NAMES A TARGET.'],
            'COPY THE TARGET.',
            '{word}. LONDON KNOWS BEFORE THE SHIPS ARRIVE. NOBODY ASKS HOW.',
            'THE TRAFFIC STOPS. THE GUNS DO NOT.', 'harbour'),
    ]),
    dict(title='LUSITANIA', intro=[
        'MAY 1915. A U-BOAT OFF THE IRISH COAST REPORTS EVERY NIGHT.',
        'YOU KNOW ITS OPERATOR BY HIS FIST: A LAZY SWING ON THE DAHS.',
        'THE LUSITANIA HAS SAILED FROM NEW YORK. TWO THOUSAND ABOARD.'], beats=[
        new_mission('decode', 'THE SWING', [
            'THE U-BOAT SENDS ITS POSITION. THE SAME LAZY DAHS.'],
            'COPY THE POSITION.',
            '{word}. RIGHT ACROSS THE LINER ROUTE.',
            'THE U-BOAT DIVES. THE SEA GOES QUIET.', 'harbour'),
        new_mission('encode', 'WARNING', [
            'YOU WIRE THE ADMIRALTY. DIVERT THE LINER.',
            'THEY HAVE THEIR REASONS. THEY DO NOT SHARE THEM.'],
            'SEND THE WARNING ANYWAY.',
            'RECEIVED. FILED. NOTHING IS DONE.',
            'THE LINE IS DEAD.', 'harbour'),
        new_mission('decode', 'EIGHTEEN MINUTES', [
            '7 MAY. 1410. A CALL FROM OFF THE OLD HEAD OF KINSALE.',
            'LUSITANIA. COME AT ONCE. BIG LIST.'],
            'COPY IT.',
            '{word}. AGAIN. EIGHTEEN MINUTES. 1,198 DEAD. YOU WERE TOO FAR.',
            'YOU MISS IT. IT WOULD NOT HAVE MATTERED. LISTEN AGAIN.', 'harbour', word='SOS'),
    ]),
    dict(title='ZEPPELINS', intro=[
        'SEPTEMBER 1916. GERMAN AIRSHIPS BOMB LONDON BY NIGHT.',
        'THEY ASK THEIR OWN STATIONS FOR BEARINGS. EVERY ASK GIVES THEM AWAY.',
        'YOU HAVE A DIRECTION-FINDING SET NOW, AND NO SLEEP.'], beats=[
        new_mission('decode', 'THE BEARING', [
            'AN AIRSHIP ASKS FOR A BEARING. IT SENDS TOO LONG, TOO OFTEN.',
            'THE DAHS SWING. YOU KNOW THAT FIST. THE U-BOAT MAN HAS WINGS NOW.'],
            'COPY THE CALL SIGN.',
            '{word}. THE BEARINGS CROSS OVER ESSEX. YOU HAVE HIM.',
            'THE AIRSHIP GOES QUIET OVER THE SEA.', 'wireless'),
        new_mission('encode', 'NIGHT FIGHTERS', [
            'THE FIGHTERS AT THE AIRFIELD NEED A HEIGHT AND A HEADING.'],
            'SEND THE INTERCEPT ORDER.',
            'THE AIRSHIP BURNS OVER ESSEX. YOU WATCH IT FROM THE STATION ROOF.',
            'THE FIGHTERS CLIMB INTO EMPTY SKY.', 'air'),
        new_mission('decode', 'ONE SURVIVOR', [
            'ONE MAN WALKED OUT OF THE WRECK: THE WIRELESS OPERATOR.',
            'IN HIS CELL HE TAPS ON THE PIPES. HE THINKS NO ONE CAN READ IT.'],
            'COPY WHAT HE TAPS.',
            '{word}. HIS NAME IS BRANDT. HE TAPS WITH A LAZY SWING.',
            'HE STOPS. HE HAS HEARD YOU BREATHING BEHIND THE WALL.', 'wireless'),
    ]),
    dict(title='ZIMMERMANN', intro=[
        'JANUARY 1917. BRANDT IS IN A CAMP. THE WAR IS NOT.',
        'A LONG TELEGRAM GOES FROM BERLIN TO WASHINGTON, IN CODE.',
        'ROOM 40 HAS A COPY. IT NEEDS EVERY GROUP, CLEAN.'], beats=[
        new_mission('decode', 'THE GROUPS', [
            'THE GROUPS COME DOWN THE WIRE FROM THE CABLE OFFICE.',
            'ONE WRONG LETTER AND THE CODEBREAKERS LOSE A WEEK.'],
            'COPY THE GROUP.',
            '{word}. THE CODEBREAKERS ASK FOR YOU BY NAME. THEN FORGET IT.',
            'A GARBLED GROUP. SOMEONE IN ROOM 40 SWEARS.', 'wireless'),
        new_mission('decode', 'IN CLEAR', [
            'ONE WORD COMES OUT OF THE CODE, THEN ANOTHER.',
            'GERMANY OFFERS MEXICO AN ALLIANCE. AND TEXAS.'],
            'COPY THE WORD.',
            '{word}. YOU UNDERSTAND WHAT YOU ARE HOLDING. AMERICA WILL COME IN.',
            'THE WORD SLIPS AWAY. ASK FOR IT AGAIN.', 'wireless'),
        new_mission('encode', 'COVER STORY', [
            'THE AMERICANS MUST BELIEVE IT CAME FROM ANYWHERE BUT ROOM 40.',
            "THE COVER WORD FOR 'A CLEVER SPY IN MEXICO' IS '{word}'."],
            'SEND THE COVER WORD.',
            'APRIL 1917. AMERICA DECLARES WAR. THE PAPERS PRAISE A CLEVER SPY.',
            'THE LINE DROPS. THE SECRET HOLDS. FOR NOW.', 'rail'),
    ]),
    dict(title='ARMISTICE', intro=[
        'NOVEMBER 1918. THE GUNS ARE TO STOP AT ELEVEN.',
        'THE ORDER MUST REACH EVERY SHIP AND EVERY TRENCH SET.',
        'UNTIL ELEVEN, MEN ARE STILL DYING.'], beats=[
        new_mission('decode', 'THE TOWER', [
            'THE EIFFEL TOWER STATION SENDS THE TERMS TO THE WORLD.'],
            'COPY THE CODE WORD.',
            '{word}. HOSTILITIES CEASE AT 1100. YOU READ IT TWICE.',
            'THE TOWER FADES. IT WILL REPEAT. LISTEN.', 'wireless'),
        new_mission('encode', 'CEASE FIRE', [
            'A DESTROYER IN THE CHANNEL HAS NOT HEARD. ITS GUNS ARE LOADED.'],
            'SEND THE CEASE FIRE.',
            'THE GUNS FALL SILENT AT ELEVEN. SO DOES THE WAR.',
            'THE DESTROYER FIRES. SEND IT BEFORE IT FIRES AGAIN.', 'harbour'),
        new_mission('encode', 'A LETTER', [
            'A LETTER FROM LONDON IN A HAND YOU HAVE NOT SEEN IN SIX YEARS.',
            'MISS E. MARSH, NOW OF THE WAR OFFICE. SHE WOULD LIKE TO MEET.',
            'YOU ANSWER BY WIRE, OF COURSE.'],
            'SEND YOUR ANSWER.',
            'SHE WAITS FOR YOU AT THE STATION IN THE RAIN. SHE TAPS ON TABLES.',
            'YOU LOSE YOUR NERVE. THE FORM SITS UNSENT.', 'rail'),
    ]),
    dict(title='LAKEHURST', intro=[
        'MAY 1937. PEACE, OF A KIND. YOU ARE OPERATOR ON A NORTH ATLANTIC LINER.',
        'THE HINDENBURG IS INBOUND FROM FRANKFURT, LATE AGAINST HEADWINDS.',
        'HER RADIO OFFICER SWINGS HIS DAHS. BRANDT, FREE AND FLYING AGAIN.'], beats=[
        new_mission('decode', 'OLD ENEMIES', [
            'BRANDT KNOWS YOUR FIST TOO. HE SENDS A JOKE, OFF THE LOG.'],
            'COPY THE JOKE.',
            "'{word}'. YOU LAUGH ALONE IN THE RADIO ROOM. TWENTY YEARS.",
            'HE SENDS IT AGAIN, SLOWER. HE IS ENJOYING THIS.', 'wireless'),
        new_mission('encode', 'WEATHER', [
            'THE AIRSHIP WANTS THE WEATHER OVER NEW JERSEY.',
            'STORMS, CLEARING BY EVENING.'],
            'SEND THE WEATHER.',
            "BRANDT: 'DANKE. SEE YOU IN THE NEXT WAR.' YOU BOTH PRETEND IT IS FUNNY.",
            'THE AIRSHIP FLIES ON WITHOUT YOUR WEATHER.', 'wireless'),
        new_mission('decode', 'THE FLASH', [
            '1925. A PRESS FLASH ON THE NEWS CIRCUIT. THE SENDER IS SHAKING.',
            'THE HINDENBURG HAS BURNED AT THE MAST. IN THIRTY-FOUR SECONDS.'],
            'COPY THE FLASH.',
            '{word}. THIRTY-SIX DEAD. THE RADIO OFFICER LIVED. HANDS BURNED.',
            'THE FLASH IS LOST. THE WHOLE WORLD IS SENDING AT ONCE.', 'wireless'),
    ]),
    dict(title='Y STATION', intro=[
        'SEPTEMBER 1939. WAR AGAIN. TOO OLD, THEY SAY, UNTIL THEY HEAR YOU.',
        'A HUT IN THE MIDLANDS. FORTY RECEIVERS. GERMAN TRAFFIC IN GROUPS.',
        'IT GOES TO A PLACE CALLED STATION X. NO ONE TELLS YOU WHY.'], beats=[
        new_mission('decode', 'THE MACHINE', [
            'A LUFTWAFFE NET, FAST AND CLEAN.',
            'A MACHINE CIPHER. THE GERMANS CALL IT UNBREAKABLE.'],
            'COPY THE GROUP.',
            '{word}. INTO THE BASKET. A MOTORCYCLE TAKES THE BASKET SOUTH.',
            'GONE. THE OPERATOR NEXT TO YOU GOT IT. THIS TIME.', 'air'),
        new_mission('decode', 'A LAZY OPERATOR', [
            'ONE GERMAN OPERATOR BEGINS EVERY MESSAGE WITH THE SAME WORD.',
            'STATION X CALLS THAT A CRIB. A CRIB OPENS A WHOLE DAY OF TRAFFIC.'],
            'COPY HIS FAVOURITE WORD.',
            '{word}. YOU CIRCLE IT TWICE IN RED PENCIL.',
            'HE SENDS TOO FAST. WAIT FOR TOMORROW. HE WILL SEND IT AGAIN.', 'air'),
        new_mission('encode', 'THE CRIB', [
            'YOUR SUPERVISOR WANTS THE CRIB FLAGGED TO STATION X AT ONCE.'],
            'SEND THE CRIB.',
            'BY MIDNIGHT STATION X IS READING THE LUFTWAFFE. YOU ARE NOT TOLD.',
            'THE TELEPRINTER JAMS.', 'wireless', echo=True),
    ]),
    dict(title='DUNKIRK', intro=[
        'MAY 1940. THE ARMY IS TRAPPED ON A BEACH IN FRANCE.',
        'EVERY BOAT ON THE SOUTH COAST IS GOING TO FETCH IT.',
        'THE LITTLE BOATS HAVE NO RADIOS. THE DESTROYERS DO.'], beats=[
        new_mission('decode', 'THE BEACH', [
            'A DESTROYER OFF THE BEACH REPORTS WHERE THE MEN ARE THICKEST.'],
            'COPY THE BEACH CODE.',
            '{word}. THE LITTLE BOATS TURN TOWARD IT.',
            'THE DESTROYER IS SHELLED OFF THE AIR. IT COMES BACK. LISTEN.', 'sea'),
        new_mission('encode', 'DAWN RAID', [
            'STATION X HAS READ A LUFTWAFFE ORDER: A RAID AT FIRST LIGHT.',
            'NO ONE CAN SAY HOW THEY KNOW. YOU SEND IT AS A HUNCH.'],
            'WARN THE DESTROYERS.',
            'THE SHIPS SCATTER AT DAWN. THE BOMBS FALL INTO EMPTY WATER.',
            'THE WARNING ARRIVES WITH THE BOMBS.', 'air'),
        new_mission('decode', 'THE COUNT', [
            '4 JUNE. THE LAST SHIP REPORTS HOW MANY CAME HOME.'],
            'COPY THE CODE WORD.',
            '{word}. 338,000 MEN. THE PAPERS CALL IT A MIRACLE.',
            'THE SIGNAL BREAKS UP. IT WILL COME AGAIN.', 'sea'),
    ]),
    dict(title='BISMARCK', intro=[
        'MAY 1941. THE BISMARCK HAS SUNK THE HOOD. 1,415 DEAD. THREE LIVED.',
        'THEN THE BISMARCK VANISHES INTO THE ATLANTIC.',
        'THE WHOLE NAVY IS LOOKING FOR HER. YOU ARE LISTENING.'], beats=[
        new_mission('decode', 'THE LONG SIGNAL', [
            'HER ADMIRAL THINKS HE IS STILL SHADOWED. HE SENDS FOR HALF AN HOUR.',
            'A LONG SIGNAL IS A BEARING, IF YOU ARE QUICK.'],
            'COPY HIS CALL SIGN.',
            '{word}. THE BEARINGS CROSS. SHE IS RUNNING FOR FRANCE.',
            'THE BEARING IS WIDE. LISTEN AGAIN.', 'harbour'),
        new_mission('decode', 'A FATHER', [
            'A LUFTWAFFE GENERAL ASKS WHERE THE BISMARCK IS GOING.',
            'HIS SON IS ABOARD. HE ASKS ON A NET STATION X CAN READ.'],
            'COPY THE ANSWER.',
            '{word}. A FATHER WORRIED FOR HIS SON. IT WILL KILL THE SON.',
            'THE ANSWER IS LOST. THE GENERAL WILL ASK AGAIN.', 'air', word='BREST'),
        new_mission('encode', 'SWORDFISH', [
            'OLD BIPLANES ON THE ARK ROYAL ARE WAITING FOR A HEADING.'],
            'SEND THE HEADING.',
            'A TORPEDO JAMS HER RUDDER. THE BISMARCK CAN ONLY TURN IN CIRCLES.',
            'THE BIPLANES SEARCH AN EMPTY SEA.', 'air'),
    ]),
    dict(title='PIANIST', intro=[
        '1943. A WOMAN IN UNIFORM COMES TO THE HUT. EVELYN MARSH.',
        'SHE RUNS SIGNALS FOR A SERVICE THAT SENDS AGENTS INTO FRANCE.',
        'ITS RADIO OPERATORS ARE CALLED PIANISTS. THEY LAST ABOUT SIX WEEKS.',
        'SHE NEEDS THE BEST FIST IN ENGLAND. SHE IS SORRY TO ASK.'], beats=[
        new_mission('encode', 'SECURITY CHECK', [
            'EVERY PIANIST HAS A SECRET MISTAKE TO MAKE ON PURPOSE.',
            'IF THE MISTAKE IS MISSING, LONDON KNOWS YOU HAVE BEEN TAKEN.'],
            'SEND YOUR CHECK WORD.',
            "MARSH: 'GOOD. NEVER FORGET IT. NEVER SEND IT IF THEY HAVE YOU.'",
            'WRONG. AGAIN. YOUR LIFE WILL DEPEND ON THIS.', 'wireless'),
        new_mission('encode', 'THE DROP', [
            'A MOONLESS NIGHT OVER THE DORDOGNE. A STATIC LINE. A FIELD.',
            'A TORCH FLASHES A LETTER FROM THE DARK. ANSWER WITH YOURS.'],
            'FLASH THE ANSWER.',
            'HANDS PULL YOU OUT OF THE WHEAT. YOU ARE IN FRANCE.',
            'NO ANSWER FROM THE FIELD. THE PILOT CIRCLES ONCE MORE.', 'air'),
        new_mission('decode', 'FIRST CONTACT', [
            'YOUR SET IS IN A SUITCASE IN A BARN. LONDON CALLS AT 2100.',
            'MARSH IS ON THE KEY HERSELF. YOU KNOW HER FIST.'],
            'COPY LONDON.',
            "{word}. THEN, OFF THE SCHEDULE: 'TAKE CARE, CORUJA.'",
            'THE SCHEDULE PASSES. LONDON WILL TRY AGAIN TOMORROW.', 'wireless'),
    ]),
    dict(title='THE VAN', intro=[
        'SPRING 1944. GERMAN DIRECTION-FINDING VANS PROWL THE LANES AT NIGHT.',
        'THEIR BEST HUNTER IS AN OLD RADIO MAN WITH BURNED HANDS.',
        'BRANDT. HE IS LISTENING FOR A FIST HE KNOWS.',
        'SEND IN UNDER FIVE MINUTES. NEVER TWICE FROM THE SAME HOUSE.'], beats=[
        new_mission('encode', 'FIVE MINUTES', [
            'LONDON WANTS THE RAILWAY TIMETABLES. THE VAN IS ON THE MAIN ROAD.'],
            'SEND IT AND GET OFF THE AIR.',
            'OFF THE AIR. THE VAN DRIVES PAST THE FARM GATE. AND PAST.',
            'THE VAN SLOWS AT THE GATE. YOU RUN. TRY AGAIN TOMORROW.', 'road'),
        new_mission('decode', 'BRANDT CALLS', [
            'ON YOUR OWN FREQUENCY, A LAZY SWING ON THE DAHS. NOT LONDON.',
            'BRANDT IS SENDING TO YOU. HE WANTS YOU TO KNOW HE KNOWS.'],
            'COPY BRANDT.',
            "{word}. THEN: 'HELLO, CORUJA.' HE KNOWS YOUR NAME NOW.",
            'HE STOPS. HE CAN WAIT. HE IS GOOD AT WAITING.', 'road'),
        new_mission('encode', 'BLOWN', [
            'YOU MOVE THE SET IN A CART OF TURNIPS TO A MILL BY THE RIVER.',
            'LONDON MUST KNOW THE OLD SCHEDULE IS BLOWN.'],
            'SEND THE ALARM.',
            "MARSH: 'UNDERSTOOD. COME HOME.' YOU DO NOT ANSWER THAT PART.",
            'THE CART LOSES A WHEEL. SET IT UP AGAIN.', 'road'),
    ]),
    dict(title='VIOLINS', intro=[
        'JUNE 1944. THE BBC FRENCH SERVICE READS NONSENSE POEMS AFTER THE NEWS.',
        'THE LONG SOBS OF THE VIOLINS OF AUTUMN. THE INVASION IS COMING.',
        'THE RESISTANCE WILL CUT EVERY RAILWAY. ON YOUR WORD.'], beats=[
        new_mission('decode', 'THE POEM', [
            '5 JUNE. THE SECOND LINE OF THE POEM. IT MEANS TOMORROW.',
            'LONDON CONFIRMS BY KEY. YOUR CIRCUIT HAS ITS OWN ACTION WORD.'],
            'COPY THE ACTION WORD.',
            '{word}. YOU CYCLE FARM TO FARM. BY MIDNIGHT THE RAILS ARE MINED.',
            'THE SET HOWLS. LONDON REPEATS.', 'wireless'),
        new_mission('encode', 'THE VIADUCT', [
            'THE MAQUIS WILL BLOW THE VIADUCT ON YOUR SIGNAL.',
            'A TROOP TRAIN IS DUE.'],
            'SEND THE SIGNAL.',
            'THE VIADUCT FALLS INTO THE RIVER. NOTHING CROSSES FOR A WEEK.',
            'THE TRAIN CROSSES. WAIT FOR THE NEXT ONE.', 'rail'),
        new_mission('decode', 'THE TANKS', [
            '6 JUNE. THE LANDINGS HAVE BEGUN IN NORMANDY. NOT HERE.',
            'HERE, AN SS PANZER DIVISION IS STARTING NORTH TO MEET THEM.'],
            "COPY THE DIVISION'S ROUTE.",
            '{word}. EVERY DAY THEY ARE LATE IS A BEACH THAT HOLDS.',
            'A FARMER GARBLES IT. HE WILL SAY IT AGAIN.', 'road'),
    ]),
    dict(title='LAST SIGNAL', intro=[
        '9 JUNE 1944. THE PANZERS WILL CROSS THE RIVER AT DAWN, AT ONE BRIDGE.',
        'THE BOMBERS CAN STOP THEM, IF THEY KNOW WHICH BRIDGE. ONLY YOU KNOW.',
        'IT IS A LONG MESSAGE. BRANDT IS ONE VILLAGE AWAY.',
        'YOU BOLT THE MILL DOOR AND OPEN THE SUITCASE.'], beats=[
        new_mission('encode', 'THE BRIDGE', [
            'THE BRIDGE FIRST. FIVE MINUTES WILL NOT BE ENOUGH.',
            'SEND IT ANYWAY.'],
            'SEND THE BRIDGE.',
            'LONDON ACKNOWLEDGES. HEADLAMPS ON THE RIVER ROAD.',
            'THE SIGNAL BREAKS UP. SEND IT AGAIN.', 'road'),
        new_mission('encode', 'THE HOUR', [
            'NOW THE HOUR. THE VAN STOPS OUTSIDE. BOOTS ON THE GRAVEL.',
            'THE BACK WINDOW IS OPEN. YOU STAY ON THE KEY.'],
            'SEND THE HOUR.',
            'ACKNOWLEDGED. THE DOOR SHAKES UNDER A RIFLE BUTT.',
            'THEY CUT THE POWER. THE BATTERY. QUICKLY.', 'road'),
        new_mission('encode', 'NO CHECK', [
            'THE DOOR IS GIVING. TIME FOR ONE MORE WORD.',
            'YOU LEAVE OUT YOUR SECURITY CHECK, SO LONDON WILL KNOW.',
            'MARSH IS ON THE KEY. SHE WILL KNOW YOUR FIST.'],
            'SEND THE LAST WORD.',
            'SENT. THE DOOR GIVES. YOU TAKE YOUR HAND OFF THE KEY.',
            'THEY ARE IN THE HALL. ONE MORE TRY.', 'road'),
    ]),
]
ENDING_EN = [
    'THE BRIDGE FALLS AT DAWN. THE PANZERS REACH NORMANDY TOO LATE.',
    'IN LONDON, MARSH LOGS A LAST MESSAGE WITH NO SECURITY CHECK.',
    'THE FILES ARE SEALED FOR FIFTY YEARS. NO ONE THANKS A NUMBER.',
    'SHE KEYS ONE REPLY INTO THE SILENCE:  SK, CORUJA. END OF WORK.',
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
    dict(title='SALA DE RÁDIO', intro=[
        'ABRIL DE 1912. RMS CARPATHIA, DE NOVA YORK PARA FIUME.',
        'TELEGRAFISTA DA NOITE. A TRIPULAÇÃO TE APELIDA DE CORUJA. O APELIDO PEGA.',
        'OS PASSAGEIROS PAGAM POR PALAVRA PARA CONTAR AO MUNDO QUE ESTÃO NO MAR.',
        'PARA ECONOMIZAR, USAM O LIVRO DE CÓDIGOS: UMA PALAVRA POR FRASE.'], beats=[
        new_mission('encode', 'O PRIMEIRO TELEGRAMA', [
            'A SRA. PEABODY, DE OHIO, QUER QUE A IRMÃ SAIBA QUE A SOPA ESTAVA FRIA.',
            "NO LIVRO DE CÓDIGOS ISSO É '{word}'. PAGO ADIANTADO."],
            'ENVIE A PALAVRA-CÓDIGO PARA CAPE RACE.',
            'CAPE RACE CONFIRMA. A SRA. PEABODY TE DÁ UM CENTAVO DE GORJETA.',
            'CAPE RACE SOME. A SRA. PEABODY RECLAMA COM O COMISSÁRIO.', 'sea'),
        new_mission('decode', 'O NOTICIÁRIO', [
            '23H. CAPE RACE TRANSMITE AS NOTÍCIAS DA NOITE.',
            'O CAPITÃO ROSTRON GOSTA DE LER OS PLACARES DE BEISEBOL TOMANDO CHOCOLATE.'],
            'COPIE A PALAVRA-CÓDIGO.',
            "'{word}'. O CAPITÃO RESMUNGA. SERVE.",
            'AS NOTÍCIAS AFUNDAM NA ESTÁTICA. O CHOCOLATE ESFRIA.', 'sea'),
        new_mission('encode', 'UMA RECLAMAÇÃO', [
            'UM CAVALHEIRO DA PRIMEIRA CLASSE ESTÁ ENJOADO E PESSIMISTA.',
            "O CORRETOR DELE PRECISA RECEBER '{word}' JÁ. QUER DIZER: VENDA TUDO."],
            'ENVIE ANTES QUE ELE VOLTE.',
            'ENVIADO. O CAVALHEIRO VOLTA PARA A CAMA. A BOLSA NEM PERCEBE.',
            'ELE VOLTA. E TRAZ A ESPOSA.', 'sea'),
    ]),
    dict(title='NOITE CHEIA', intro=[
        'O GRANDE NAVIO NOVO ESTÁ TRANSMITINDO, EM PLENA VIAGEM INAUGURAL.',
        'TITANIC. INDICATIVO MGY. OS TELEGRAFISTAS ESTÃO ATOLADOS DE MENSAGENS.',
        'TODO MILIONÁRIO A BORDO QUER TELEGRAFAR PARA O MORDOMO.'], beats=[
        new_mission('decode', 'RETRANSMISSÃO', [
            'MGY PEDE QUE VOCÊ RETRANSMITA UMA MENSAGEM QUE A COSTA NÃO OUVE.',
            'DE UMA TAL SRTA. EVELYN MARSH, DEZENOVE ANOS, PARA A TIA.'],
            'COPIE A PALAVRA-CÓDIGO DA SRTA. MARSH.',
            "'{word}': O CACHORRO ENJOOU. EU NÃO. MELHOR VIAGEM DA MINHA VIDA.",
            'A RETRANSMISSÃO FALHA. A TIA NUNCA VAI SABER DO CACHORRO.', 'sea'),
        new_mission('encode', 'PASSE ADIANTE', [
            'A TIA PRECISA RECEBER HOJE.',
            'PASSE PARA A PRÓXIMA ESTAÇÃO, EXATAMENTE COMO OUVIU.'],
            'ENVIE A PALAVRA DA SRTA. MARSH.',
            'RECEBIDO. EM SOUTHAMPTON, UMA TIA RESPIRA ALIVIADA POR UM CACHORRO.',
            'A ESTAÇÃO NÃO RESPONDE.', 'sea', echo=True),
        new_mission('decode', 'GELO', [
            'UM VAPOR MAIS AO NORTE AVISA SOBRE GELO A QUEM QUISER OUVIR.',
            'O MGY MANDA O VAPOR CALAR A BOCA. ESTÁ OCUPADO DEMAIS.'],
            'COPIE O AVISO DE GELO.',
            "'{word}'. VOCÊ PREGA O AVISO ACIMA DA TECLA. GELO NA ROTA TODA.",
            'O AVISO SE PERDE NO FALATÓRIO DOS PASSAGEIROS DO MGY.', 'ice'),
    ]),
    dict(title='VENHAM JÁ', intro=[
        '14 DE ABRIL DE 1912. 23H35. SEU TURNO ACABOU. VOCÊ JÁ TIROU UMA BOTA.',
        'VOCÊ FICA COM OS FONES MAIS UM POUCO, PARA PASSAR UMA NOTÍCIA AO MGY.',
        'O MGY RESPONDE ANTES DE VOCÊ TERMINAR.'], beats=[
        new_mission('decode', 'SOCORRO', [
            'TITANIC: VENHAM JÁ. BATEMOS NUM ICEBERG.',
            'DEPOIS, O SINAL NOVO, QUE NINGUÉM AINDA TINHA OUVIDO A SÉRIO.'],
            'COPIE A CHAMADA.',
            '{word}. VOCÊ CORRE PARA A PONTE COM UMA BOTA SÓ.',
            'DEVE SER BRINCADEIRA. NÃO É. ESCUTE DE NOVO.', 'ice', word='SOS'),
        new_mission('encode', 'A TODO VAPOR', [
            'O CAPITÃO ROSTRON VIRA O NAVIO ANTES DE TERMINAR DE SE VESTIR.',
            'CINQUENTA E OITO MILHAS. QUATRO HORAS A TODO VAPOR, NO GELO.'],
            'AVISE QUE VOCÊS ESTÃO A CAMINHO.',
            "MGY: 'VENHAM O MAIS RÁPIDO POSSÍVEL. A CASA DE MÁQUINAS ESTÁ ALAGANDO.'",
            'O MGY CONTINUA CHAMANDO. ELES NÃO SABEM QUE ALGUÉM OUVIU.', 'ice'),
        new_mission('decode', 'A ÚLTIMA PALAVRA', [
            '1H27. O MGY ESTÁ FRACO AGORA. A ENERGIA ESTÁ ACABANDO.',
            'MAIS UMA PALAVRA DO NAVIO QUE AFUNDA.'],
            'COPIE.',
            '{word}. DEPOIS, ESTÁTICA. SÓ ESTÁTICA.',
            'A ESTÁTICA LEVA A PALAVRA. ESCUTE. POR FAVOR.', 'ice'),
    ]),
    dict(title='NOMES', intro=[
        '4H10. BOTES SALVA-VIDAS NA LUZ CINZENTA. NENHUM NAVIO. SÓ GELO E DESTROÇOS.',
        'O CARPATHIA RECOLHE 705 ALMAS. O MUNDO GRITA POR NOTÍCIAS.',
        'O CAPITÃO ORDENA: PRIMEIRO OS NOMES DOS SOBREVIVENTES. NADA PARA A IMPRENSA.'],
        beats=[
        new_mission('encode', 'A LISTA', [
            'NOME APÓS NOME, TRINTA HORAS SEM DORMIR.',
            "A PRÓXIMA FAMÍLIA PEDIU UMA PALAVRA-CÓDIGO: '{word}'. QUER DIZER VIVO."],
            'ENVIE.',
            'CONFIRMADO. EM ALGUM LUGAR, UMA FAMÍLIA PARA DE ESPERAR.',
            'SUA MÃO TRAVA. A ESTAÇÃO EM TERRA PERDE O SEU SINAL.', 'sea'),
        new_mission('decode', 'UM NOME CONHECIDO', [
            'NA LISTA: MARSH, E., SRTA. VIVA. ELA APARECE NA SALA DE RÁDIO.',
            'APRENDEU MORSE OLHANDO OS TELEGRAFISTAS DO TITANIC.',
            'ELA BATE A MENSAGEM NA SUA MESA COM UM LÁPIS.'],
            'LEIA O QUE ELA BATE.',
            "'{word}'. PARA A TIA. O CACHORRO NÃO SOBREVIVEU.",
            'ELA BATE RÁPIDO DEMAIS. E RI, PELA PRIMEIRA VEZ EM DOIS DIAS.', 'sea'),
        new_mission('encode', 'A TIA', [
            'A MESMA TIA. A MESMA ESTAÇÃO. OUTRO TIPO DE MENSAGEM.'],
            'ENVIE A PALAVRA DA SRTA. MARSH.',
            'A TIA RESPONDE EM QUATRO MINUTOS. A SRTA. MARSH ENFIM CHORA.',
            'A LINHA ESTÁ ENTUPIDA DE TRÁFEGO DA IMPRENSA.', 'sea', echo=True),
    ]),
    dict(title='SALA 40', intro=[
        'AGOSTO DE 1914. GUERRA.',
        'UM HOMEM DO ALMIRANTADO SABE QUEM MANTEVE O CARPATHIA NO AR.',
        'ELE QUER ESSE OUVIDO NA COSTA DE NORFOLK, ESCUTANDO A FROTA ALEMÃ.',
        'OS GRUPOS QUE VOCÊ COPIA VÃO PARA UMA SALA EM LONDRES. A SALA 40.'], beats=[
        new_mission('decode', 'INTERCEPTAÇÃO', [
            'TRÁFEGO NAVAL ALEMÃO. GRUPOS DE LETRAS QUE NÃO SIGNIFICAM NADA PARA VOCÊ.',
            'NINGUÉM TE DIZ O QUE SIGNIFICAM. SÓ TE DIZEM PARA NÃO PERDER NENHUM.'],
            'COPIE O GRUPO.',
            '{word}. UM MOTOCICLISTA LEVA PARA LONDRES. NINGUÉM AGRADECE.',
            'O GRUPO SE FOI. ALGUÉM EM LONDRES FICA COM UMA LACUNA NA PÁGINA.',
            'wireless'),
        new_mission('encode', 'A LINHA TELEGRÁFICA', [
            'A SALA 40 QUER CADA GRUPO EM MENOS DE UMA HORA.',
            'ELES TÊM UM LIVRO DE CÓDIGOS ALEMÃO CAPTURADO. NINGUÉM TE CONTA.'],
            'PASSE O GRUPO PARA LONDRES.',
            'LONDRES CONFIRMA. ALGUÉM ABRE UM LIVRO QUE VOCÊ NUNCA VAI VER.',
            'A LINHA ESTÁ OCUPADA. LONDRES ESPERA.', 'wireless', echo=True),
        new_mission('decode', 'O ATAQUE', [
            'DEZEMBRO. A ESQUADRA ALEMÃ ESTÁ NO MAR. O TRÁFEGO DOBRA.',
            'UM TELEGRAFISTA DESCUIDADO DIZ O NOME DE UM ALVO.'],
            'COPIE O ALVO.',
            '{word}. LONDRES SABE ANTES DE OS NAVIOS CHEGAREM. NINGUÉM PERGUNTA COMO.',
            'O TRÁFEGO PARA. OS CANHÕES, NÃO.', 'harbour'),
    ]),
    dict(title='LUSITANIA', intro=[
        'MAIO DE 1915. UM SUBMARINO NA COSTA DA IRLANDA TRANSMITE TODA NOITE.',
        'VOCÊ CONHECE O TELEGRAFISTA PELA BATIDA: UM BALANÇO PREGUIÇOSO NOS TRAÇOS.',
        'O LUSITANIA SAIU DE NOVA YORK. DUAS MIL PESSOAS A BORDO.'], beats=[
        new_mission('decode', 'O BALANÇO', [
            'O SUBMARINO MANDA A POSIÇÃO. OS MESMOS TRAÇOS PREGUIÇOSOS.'],
            'COPIE A POSIÇÃO.',
            '{word}. BEM NA ROTA DOS TRANSATLÂNTICOS.',
            'O SUBMARINO MERGULHA. O MAR SILENCIA.', 'harbour'),
        new_mission('encode', 'O AVISO', [
            'VOCÊ TELEGRAFA AO ALMIRANTADO: DESVIEM O NAVIO.',
            'ELES TÊM SEUS MOTIVOS. NÃO OS COMPARTILHAM.'],
            'ENVIE O AVISO MESMO ASSIM.',
            'RECEBIDO. ARQUIVADO. NADA É FEITO.',
            'A LINHA ESTÁ MUDA.', 'harbour'),
        new_mission('decode', 'DEZOITO MINUTOS', [
            '7 DE MAIO. 14H10. UMA CHAMADA AO LARGO DE OLD HEAD OF KINSALE.',
            'LUSITANIA. VENHAM JÁ. ADERNANDO MUITO.'],
            'COPIE.',
            '{word}. DE NOVO. DEZOITO MINUTOS. 1.198 MORTOS. VOCÊ ESTAVA LONGE DEMAIS.',
            'VOCÊ NÃO PEGOU. NÃO TERIA FEITO DIFERENÇA. ESCUTE DE NOVO.', 'harbour', word='SOS'),
    ]),
    dict(title='ZEPELINS', intro=[
        'SETEMBRO DE 1916. DIRIGÍVEIS ALEMÃES BOMBARDEIAM LONDRES À NOITE.',
        'ELES PEDEM MARCAÇÕES ÀS PRÓPRIAS ESTAÇÕES. CADA PEDIDO OS DENUNCIA.',
        'AGORA VOCÊ TEM UM RADIOGONIÔMETRO, E NENHUMA NOITE DE SONO.'], beats=[
        new_mission('decode', 'A MARCAÇÃO', [
            'UM DIRIGÍVEL PEDE MARCAÇÃO. TRANSMITE DEMAIS, E COM FREQUÊNCIA DEMAIS.',
            'OS TRAÇOS BALANÇAM. É AQUELA BATIDA. O HOMEM DO SUBMARINO AGORA VOA.'],
            'COPIE O INDICATIVO.',
            '{word}. AS MARCAÇÕES SE CRUZAM SOBRE ESSEX. VOCÊ O ENCONTROU.',
            'O DIRIGÍVEL SILENCIA SOBRE O MAR.', 'wireless'),
        new_mission('encode', 'CAÇAS NOTURNOS', [
            'OS CAÇAS NO CAMPO DE POUSO PRECISAM DE ALTITUDE E RUMO.'],
            'ENVIE A ORDEM DE INTERCEPTAR.',
            'O DIRIGÍVEL QUEIMA SOBRE ESSEX. VOCÊ ASSISTE DO TELHADO DA ESTAÇÃO.',
            'OS CAÇAS SOBEM PARA UM CÉU VAZIO.', 'air'),
        new_mission('decode', 'UM SOBREVIVENTE', [
            'UM HOMEM SAIU ANDANDO DOS DESTROÇOS: O TELEGRAFISTA.',
            'NA CELA, ELE BATE NOS CANOS. ACHA QUE NINGUÉM SABE LER AQUILO.'],
            'COPIE O QUE ELE BATE.',
            '{word}. O NOME DELE É BRANDT. ELE BATE COM UM BALANÇO PREGUIÇOSO.',
            'ELE PARA. OUVIU VOCÊ RESPIRAR DO OUTRO LADO DA PAREDE.', 'wireless'),
    ]),
    dict(title='ZIMMERMANN', intro=[
        'JANEIRO DE 1917. BRANDT ESTÁ NUM CAMPO DE PRISIONEIROS. A GUERRA, NÃO.',
        'UM TELEGRAMA LONGO VAI DE BERLIM PARA WASHINGTON, EM CÓDIGO.',
        'A SALA 40 TEM UMA CÓPIA. PRECISA DE CADA GRUPO, LIMPO.'], beats=[
        new_mission('decode', 'OS GRUPOS', [
            'OS GRUPOS CHEGAM PELO FIO, VINDOS DA ESTAÇÃO DO CABO SUBMARINO.',
            'UMA LETRA ERRADA E OS DECIFRADORES PERDEM UMA SEMANA.'],
            'COPIE O GRUPO.',
            '{word}. OS DECIFRADORES PEDEM POR VOCÊ PELO NOME. DEPOIS ESQUECEM.',
            'UM GRUPO TRUNCADO. ALGUÉM NA SALA 40 PRAGUEJA.', 'wireless'),
        new_mission('decode', 'EM CLARO', [
            'UMA PALAVRA EMERGE DO CÓDIGO. DEPOIS OUTRA.',
            'A ALEMANHA OFERECE AO MÉXICO UMA ALIANÇA. E O TEXAS.'],
            'COPIE A PALAVRA.',
            '{word}. VOCÊ ENTENDE O QUE TEM NAS MÃOS. OS EUA VÃO ENTRAR NA GUERRA.',
            'A PALAVRA ESCAPA. PEÇA DE NOVO.', 'wireless'),
        new_mission('encode', 'A HISTÓRIA DE FACHADA', [
            'OS AMERICANOS PRECISAM ACHAR QUE VEIO DE QUALQUER LUGAR MENOS DA SALA 40.',
            "O CÓDIGO PARA 'UM ESPIÃO ESPERTO NO MÉXICO' É '{word}'."],
            'ENVIE A PALAVRA DE FACHADA.',
            'ABRIL DE 1917. OS EUA DECLARAM GUERRA. OS JORNAIS ELOGIAM O ESPIÃO ESPERTO.',
            'A LINHA CAI. O SEGREDO SE MANTÉM. POR ENQUANTO.', 'rail'),
    ]),
    dict(title='ARMISTÍCIO', intro=[
        'NOVEMBRO DE 1918. OS CANHÕES DEVEM PARAR ÀS ONZE.',
        'A ORDEM PRECISA CHEGAR A CADA NAVIO E A CADA RÁDIO DE TRINCHEIRA.',
        'ATÉ AS ONZE, HOMENS AINDA ESTÃO MORRENDO.'], beats=[
        new_mission('decode', 'A TORRE', [
            'A ESTAÇÃO DA TORRE EIFFEL TRANSMITE OS TERMOS AO MUNDO.'],
            'COPIE A PALAVRA-CÓDIGO.',
            '{word}. HOSTILIDADES CESSAM ÀS 11H. VOCÊ LÊ DUAS VEZES.',
            'O SINAL DA TORRE SOME. ELA VAI REPETIR. ESCUTE.', 'wireless'),
        new_mission('encode', 'CESSAR-FOGO', [
            'UM CONTRATORPEDEIRO NO CANAL NÃO OUVIU. OS CANHÕES ESTÃO CARREGADOS.'],
            'ENVIE O CESSAR-FOGO.',
            'OS CANHÕES SE CALAM ÀS ONZE. A GUERRA TAMBÉM.',
            'O NAVIO DISPARA. ENVIE ANTES QUE DISPARE DE NOVO.', 'harbour'),
        new_mission('encode', 'UMA CARTA', [
            'UMA CARTA DE LONDRES, NUMA LETRA QUE VOCÊ NÃO VÊ HÁ SEIS ANOS.',
            'SRTA. E. MARSH, AGORA DO MINISTÉRIO DA GUERRA. ELA QUER TE VER.',
            'VOCÊ RESPONDE POR TELEGRAMA, CLARO.'],
            'ENVIE SUA RESPOSTA.',
            'ELA TE ESPERA NA ESTAÇÃO, NA CHUVA. AINDA BATUCA NAS MESAS.',
            'VOCÊ PERDE A CORAGEM. O FORMULÁRIO FICA NA GAVETA.', 'rail'),
    ]),
    dict(title='LAKEHURST', intro=[
        'MAIO DE 1937. PAZ, MAIS OU MENOS. VOCÊ É TELEGRAFISTA NUM TRANSATLÂNTICO.',
        'O HINDENBURG VEM DE FRANKFURT, ATRASADO PELO VENTO CONTRA.',
        'O OFICIAL DE RÁDIO BALANÇA OS TRAÇOS. BRANDT, LIVRE E VOANDO DE NOVO.'], beats=[
        new_mission('decode', 'VELHOS INIMIGOS', [
            'BRANDT TAMBÉM CONHECE SUA BATIDA. MANDA UMA PIADA, FORA DO REGISTRO.'],
            'COPIE A PIADA.',
            "'{word}'. VOCÊ RI SOZINHO NA SALA DE RÁDIO. VINTE ANOS.",
            'ELE MANDA DE NOVO, MAIS DEVAGAR. ESTÁ SE DIVERTINDO.', 'wireless'),
        new_mission('encode', 'O TEMPO', [
            'O DIRIGÍVEL QUER A PREVISÃO DO TEMPO EM NOVA JERSEY.',
            'TEMPESTADES, MELHORANDO À NOITE.'],
            'ENVIE A PREVISÃO.',
            "BRANDT: 'DANKE. ATÉ A PRÓXIMA GUERRA.' VOCÊS FINGEM QUE TEM GRAÇA.",
            'O DIRIGÍVEL SEGUE SEM A SUA PREVISÃO.', 'wireless'),
        new_mission('decode', 'O FLASH', [
            '19H25. UM FLASH NO CIRCUITO DE NOTÍCIAS. QUEM TRANSMITE ESTÁ TREMENDO.',
            'O HINDENBURG PEGOU FOGO AO ATRACAR. QUEIMOU EM TRINTA E QUATRO SEGUNDOS.'],
            'COPIE O FLASH.',
            '{word}. TRINTA E SEIS MORTOS. O OFICIAL DE RÁDIO VIVEU. MÃOS QUEIMADAS.',
            'O FLASH SE PERDE. O MUNDO INTEIRO ESTÁ TRANSMITINDO.', 'wireless'),
    ]),
    dict(title='ESTAÇÃO Y', intro=[
        'SETEMBRO DE 1939. GUERRA DE NOVO. VELHO DEMAIS, DIZEM, ATÉ TE OUVIREM.',
        'UM BARRACÃO NO INTERIOR. QUARENTA RECEPTORES. TRÁFEGO ALEMÃO EM GRUPOS.',
        'TUDO VAI PARA UM LUGAR CHAMADO ESTAÇÃO X. NINGUÉM TE DIZ POR QUÊ.'], beats=[
        new_mission('decode', 'A MÁQUINA', [
            'UMA REDE DA LUFTWAFFE, RÁPIDA E LIMPA.',
            'UMA CIFRA DE MÁQUINA. OS ALEMÃES DIZEM QUE É INQUEBRÁVEL.'],
            'COPIE O GRUPO.',
            '{word}. NO CESTO. UM MOTOCICLISTA LEVA O CESTO PARA O SUL.',
            'PERDEU. O COLEGA DO LADO PEGOU. DESTA VEZ.', 'air'),
        new_mission('decode', 'UM TELEGRAFISTA PREGUIÇOSO', [
            'UM TELEGRAFISTA ALEMÃO COMEÇA TODA MENSAGEM COM A MESMA PALAVRA.',
            'A ESTAÇÃO X CHAMA ISSO DE COLA. UMA COLA ABRE UM DIA INTEIRO DE TRÁFEGO.'],
            'COPIE A PALAVRA FAVORITA DELE.',
            '{word}. VOCÊ CIRCULA DUAS VEZES COM LÁPIS VERMELHO.',
            'ELE É RÁPIDO DEMAIS. AMANHÃ ELE MANDA DE NOVO.', 'air'),
        new_mission('encode', 'A COLA', [
            'SEU SUPERVISOR QUER A COLA NA ESTAÇÃO X IMEDIATAMENTE.'],
            'ENVIE A COLA.',
            'À MEIA-NOITE A ESTAÇÃO X ESTÁ LENDO A LUFTWAFFE. NINGUÉM TE CONTA.',
            'O TELEIMPRESSOR TRAVA.', 'wireless', echo=True),
    ]),
    dict(title='DUNQUERQUE', intro=[
        'MAIO DE 1940. O EXÉRCITO ESTÁ ENCURRALADO NUMA PRAIA NA FRANÇA.',
        'TODO BARCO DA COSTA SUL DA INGLATERRA VAI BUSCAR OS HOMENS.',
        'OS BARQUINHOS NÃO TÊM RÁDIO. OS CONTRATORPEDEIROS TÊM.'], beats=[
        new_mission('decode', 'A PRAIA', [
            'UM CONTRATORPEDEIRO INFORMA ONDE HÁ MAIS HOMENS NA AREIA.'],
            'COPIE O CÓDIGO DA PRAIA.',
            '{word}. OS BARQUINHOS SEGUEM PARA LÁ.',
            'O NAVIO SAI DO AR SOB FOGO. ELE VOLTA. ESCUTE.', 'sea'),
        new_mission('encode', 'ATAQUE AO AMANHECER', [
            'A ESTAÇÃO X LEU UMA ORDEM DA LUFTWAFFE: ATAQUE AO NASCER DO SOL.',
            'NINGUÉM PODE DIZER COMO SABEM. VOCÊ MANDA COMO SE FOSSE UM PALPITE.'],
            'AVISE OS CONTRATORPEDEIROS.',
            'OS NAVIOS SE DISPERSAM. AS BOMBAS CAEM NA ÁGUA VAZIA.',
            'O AVISO CHEGA JUNTO COM AS BOMBAS.', 'air'),
        new_mission('decode', 'A CONTAGEM', [
            '4 DE JUNHO. O ÚLTIMO NAVIO INFORMA QUANTOS VOLTARAM.'],
            'COPIE A PALAVRA-CÓDIGO.',
            '{word}. 338 MIL HOMENS. OS JORNAIS CHAMAM DE MILAGRE.',
            'O SINAL SE DESFAZ. ELE VAI VOLTAR.', 'sea'),
    ]),
    dict(title='BISMARCK', intro=[
        'MAIO DE 1941. O BISMARCK AFUNDOU O HOOD. 1.415 MORTOS. TRÊS SOBREVIVERAM.',
        'DEPOIS O BISMARCK SOME NO ATLÂNTICO.',
        'A MARINHA INTEIRA PROCURA POR ELE. VOCÊ ESCUTA.'], beats=[
        new_mission('decode', 'O SINAL LONGO', [
            'O ALMIRANTE ACHA QUE AINDA ESTÁ SENDO SEGUIDO. TRANSMITE POR MEIA HORA.',
            'UM SINAL LONGO É UMA MARCAÇÃO, PARA QUEM FOR RÁPIDO.'],
            'COPIE O INDICATIVO DELE.',
            '{word}. AS MARCAÇÕES SE CRUZAM. ELE ESTÁ FUGINDO PARA A FRANÇA.',
            'A MARCAÇÃO SAIU IMPRECISA. ESCUTE DE NOVO.', 'harbour'),
        new_mission('decode', 'UM PAI', [
            'UM GENERAL DA LUFTWAFFE PERGUNTA PARA ONDE VAI O BISMARCK.',
            'O FILHO ESTÁ A BORDO. ELE PERGUNTA NUMA REDE QUE A ESTAÇÃO X LÊ.'],
            'COPIE A RESPOSTA.',
            '{word}. UM PAI PREOCUPADO COM O FILHO. ISSO VAI MATAR O FILHO.',
            'A RESPOSTA SE PERDE. O GENERAL VAI PERGUNTAR DE NOVO.', 'air', word='BREST'),
        new_mission('encode', 'SWORDFISH', [
            'BIPLANOS VELHOS NO ARK ROYAL ESPERAM UM RUMO.'],
            'ENVIE O RUMO.',
            'UM TORPEDO TRAVA O LEME. O BISMARCK SÓ CONSEGUE NAVEGAR EM CÍRCULOS.',
            'OS BIPLANOS VASCULHAM UM MAR VAZIO.', 'air'),
    ]),
    dict(title='PIANISTA', intro=[
        '1943. UMA MULHER DE UNIFORME CHEGA AO BARRACÃO. EVELYN MARSH.',
        'ELA COMANDA AS COMUNICAÇÕES DE UM SERVIÇO QUE MANDA AGENTES À FRANÇA.',
        'OS RADIOTELEGRAFISTAS SÃO CHAMADOS DE PIANISTAS. DURAM UMAS SEIS SEMANAS.',
        'ELA PRECISA DA MELHOR BATIDA DA INGLATERRA. LAMENTA TER DE PEDIR.'], beats=[
        new_mission('encode', 'VERIFICAÇÃO', [
            'TODO PIANISTA TEM UM ERRO SECRETO PARA COMETER DE PROPÓSITO.',
            'SE O ERRO FALTAR, LONDRES SABE QUE VOCÊ FOI PRESO.'],
            'ENVIE SUA PALAVRA DE VERIFICAÇÃO.',
            "MARSH: 'ÓTIMO. NUNCA ESQUEÇA. NUNCA ENVIE SE ELES TE PEGAREM.'",
            'ERRADO. DE NOVO. SUA VIDA VAI DEPENDER DISSO.', 'wireless'),
        new_mission('encode', 'O SALTO', [
            'NOITE SEM LUA SOBRE A DORDONHA. UM SALTO DE PARAQUEDAS. UM CAMPO.',
            'UMA LANTERNA PISCA UMA LETRA NO ESCURO. RESPONDA COM A SUA.'],
            'PISQUE A RESPOSTA.',
            'MÃOS TE PUXAM DO TRIGAL. VOCÊ ESTÁ NA FRANÇA.',
            'NENHUMA RESPOSTA DO CAMPO. O PILOTO DÁ MAIS UMA VOLTA.', 'air'),
        new_mission('decode', 'PRIMEIRO CONTATO', [
            'SEU RÁDIO ESTÁ NUMA MALA NUM CELEIRO. LONDRES CHAMA ÀS 21H.',
            'É A PRÓPRIA MARSH NA TECLA. VOCÊ CONHECE A BATIDA DELA.'],
            'COPIE LONDRES.',
            "{word}. DEPOIS, FORA DO HORÁRIO: 'CUIDE-SE, CORUJA.'",
            'O HORÁRIO COMBINADO PASSA. LONDRES TENTA AMANHÃ.', 'wireless'),
    ]),
    dict(title='O FURGÃO', intro=[
        'PRIMAVERA DE 1944. FURGÕES ALEMÃES DE RADIOGONIOMETRIA RONDAM AS ESTRADAS.',
        'O MELHOR CAÇADOR É UM VELHO RADIOTELEGRAFISTA COM AS MÃOS QUEIMADAS.',
        'BRANDT. ELE ESTÁ À ESCUTA DE UMA BATIDA QUE CONHECE BEM.',
        'TRANSMITA EM MENOS DE CINCO MINUTOS. NUNCA DUAS VEZES DA MESMA CASA.'], beats=[
        new_mission('encode', 'CINCO MINUTOS', [
            'LONDRES QUER OS HORÁRIOS DOS TRENS. O FURGÃO ESTÁ NA ESTRADA PRINCIPAL.'],
            'ENVIE E SAIA DO AR.',
            'FORA DO AR. O FURGÃO PASSA PELA PORTEIRA DA FAZENDA. E SEGUE.',
            'O FURGÃO REDUZ NA PORTEIRA. CORRA. TENTE AMANHÃ.', 'road'),
        new_mission('decode', 'BRANDT CHAMA', [
            'NA SUA PRÓPRIA FREQUÊNCIA, UM BALANÇO PREGUIÇOSO NOS TRAÇOS. NÃO É LONDRES.',
            'BRANDT ESTÁ TRANSMITINDO PARA VOCÊ. QUER QUE VOCÊ SAIBA QUE ELE SABE.'],
            'COPIE BRANDT.',
            "{word}. DEPOIS: 'OLÁ, CORUJA.' AGORA ELE SABE SEU NOME.",
            'ELE PARA. ELE PODE ESPERAR. ELE É BOM EM ESPERAR.', 'road'),
        new_mission('encode', 'QUEIMADO', [
            'VOCÊ LEVA O RÁDIO NUMA CARROÇA DE NABOS ATÉ UM MOINHO NO RIO.',
            'LONDRES PRECISA SABER QUE O HORÁRIO ANTIGO FOI DESCOBERTO.'],
            'ENVIE O ALERTA.',
            "MARSH: 'ENTENDIDO. VOLTE PARA CASA.' VOCÊ NÃO RESPONDE ESSA PARTE.",
            'A CARROÇA PERDE UMA RODA. MONTE TUDO DE NOVO.', 'road'),
    ]),
    dict(title='VIOLINOS', intro=[
        'JUNHO DE 1944. DEPOIS DO NOTICIÁRIO, A BBC LÊ RECADOS SEM SENTIDO EM FRANCÊS.',
        'OS LONGOS SOLUÇOS DOS VIOLINOS DO OUTONO. A INVASÃO ESTÁ VINDO.',
        'A RESISTÊNCIA VAI CORTAR CADA FERROVIA QUANDO VOCÊ DER A PALAVRA.'], beats=[
        new_mission('decode', 'O POEMA', [
            '5 DE JUNHO. O SEGUNDO VERSO DO POEMA. QUER DIZER AMANHÃ.',
            'LONDRES CONFIRMA EM MORSE. SUA REDE TEM UMA PALAVRA DE AÇÃO PRÓPRIA.'],
            'COPIE A PALAVRA DE AÇÃO.',
            '{word}. VOCÊ PEDALA DE FAZENDA EM FAZENDA. À MEIA-NOITE, TRILHOS MINADOS.',
            'O RÁDIO UIVA. LONDRES REPETE.', 'wireless'),
        new_mission('encode', 'O VIADUTO', [
            'OS MAQUIS VÃO EXPLODIR O VIADUTO AO SEU SINAL.',
            'UM TREM DE TROPAS ESTÁ CHEGANDO.'],
            'ENVIE O SINAL.',
            'O VIADUTO CAI NO RIO. NADA ATRAVESSA POR UMA SEMANA.',
            'O TREM PASSA. ESPERE O PRÓXIMO.', 'rail'),
        new_mission('decode', 'OS TANQUES', [
            '6 DE JUNHO. O DESEMBARQUE COMEÇOU NA NORMANDIA. NÃO AQUI.',
            'AQUI, UMA DIVISÃO PANZER DA SS PARTE PARA O NORTE AO ENCONTRO DELES.'],
            'COPIE A ROTA DA DIVISÃO.',
            '{word}. CADA DIA DE ATRASO É UMA PRAIA QUE AGUENTA.',
            'O FAZENDEIRO QUE VIU OS TANQUES SE ATRAPALHA. ELE VAI REPETIR.', 'road'),
    ]),
    dict(title='SINAL FINAL', intro=[
        '9 DE JUNHO DE 1944. OS PANZERS VÃO CRUZAR O RIO AO AMANHECER, POR UMA PONTE.',
        'OS BOMBARDEIROS PODEM DETÊ-LOS, SE SOUBEREM QUAL PONTE. SÓ VOCÊ SABE.',
        'É UMA MENSAGEM LONGA. BRANDT ESTÁ NA VILA VIZINHA.',
        'VOCÊ TRANCA A PORTA DO MOINHO E ABRE A MALA.'], beats=[
        new_mission('encode', 'A PONTE', [
            'PRIMEIRO A PONTE. CINCO MINUTOS NÃO VÃO BASTAR.',
            'ENVIE MESMO ASSIM.'],
            'ENVIE A PONTE.',
            'LONDRES CONFIRMA. FARÓIS NA ESTRADA DO RIO.',
            'O SINAL SE DESFAZ. ENVIE DE NOVO.', 'road'),
        new_mission('encode', 'A HORA', [
            'AGORA A HORA. O FURGÃO PARA LÁ FORA. BOTAS NO CASCALHO.',
            'A JANELA DOS FUNDOS ESTÁ ABERTA. VOCÊ FICA NA TECLA.'],
            'ENVIE A HORA.',
            'CONFIRMADO. A PORTA TREME SOB A CORONHA DE UM FUZIL.',
            'CORTARAM A LUZ. A BATERIA. RÁPIDO.', 'road'),
        new_mission('encode', 'SEM VERIFICAÇÃO', [
            'A PORTA ESTÁ CEDENDO. DÁ TEMPO DE MAIS UMA PALAVRA.',
            'VOCÊ OMITE SUA VERIFICAÇÃO, PARA QUE LONDRES SAIBA.',
            'MARSH ESTÁ NA TECLA. ELA VAI RECONHECER SUA BATIDA.'],
            'ENVIE A ÚLTIMA PALAVRA.',
            'ENVIADA. A PORTA CEDE. VOCÊ TIRA A MÃO DA TECLA.',
            'ELES ESTÃO NO CORREDOR. MAIS UMA TENTATIVA.', 'road'),
    ]),
]
ENDING_PT = [
    'A PONTE CAI AO AMANHECER. OS PANZERS CHEGAM ATRASADOS À NORMANDIA.',
    'EM LONDRES, MARSH REGISTRA UMA ÚLTIMA MENSAGEM SEM VERIFICAÇÃO.',
    'OS ARQUIVOS FICAM LACRADOS POR 50 ANOS. VOCÊ VIRA UM NÚMERO NUMA PASTA.',
    'ELA BATE UMA RESPOSTA NO SILÊNCIO:  SK, CORUJA. FIM DO SERVIÇO.',
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
        'title_big': 'MORSE CODE', 'subtitle': 'THE LISTENER  ·  1912 - 1944',
        'tap_hold': 'TAP SPACE = DIT {dot}        HOLD SPACE = DAH {dah}',
        'menu_begin': '[ENTER] BEGIN', 'menu_continue': '[C] CONTINUE FROM CHAPTER {n}',
        'menu_rest': '[F] PRACTICE   [L] LANGUAGE   [Q] QUIT',
        'chapter_label': 'CHAPTER {n}', 'first_letters': 'YOUR FIRST LETTERS', 'new_letters': 'NEW LETTERS',
        'review_letters': 'REVIEW: NO NEW LETTERS, MORE PRACTICE',
        'try_them': 'TRY THEM ▸ ', 'enter_begin': '[ENTER] BEGIN',
        'chapter_help': 'TAP / HOLD SPACE TO PRACTISE   [TAB] HEAR THEM AGAIN',
        'brief_line': 'CHAPTER {n} · {title}', 'code_word': 'CODE WORD:  {word}', 'ready': '[ENTER] READY',
        'encode_help': 'TAP SPACE = DIT •    HOLD SPACE = DAH ━    [TAB] HINT    [ESC] QUIT',
        'no_lamp': 'NO LAMP FROM HERE ON. LISTEN.', 'no_tape': 'NO TAPE NOW. WATCH THE LAMP, AND LISTEN.',
        'decode_help': 'TYPE THE LETTERS YOU HEAR    [TAB] REPEAT    [ESC] QUIT',
        'time_bonus': '+{bonus} TIME BONUS', 'lives_left': 'LIVES LEFT: {n}. TRY AGAIN.',
        'no_lives': 'NO LIVES LEFT.', 'continue': '[ENTER] CONTINUE',
        'practice': 'PRACTICE', 'free_help': 'TAP = DIT  ·  HOLD = DAH  ·  [BKSP] ERASE  ·  [ESC] BACK',
        'over_big': 'SIGNAL LOST', 'over_line': 'THE KEY HAS GONE SILENT.',
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
        'title_big': 'CÓDIGO MORSE', 'subtitle': 'O OUVINTE  ·  1912 - 1944',
        'tap_hold': 'TOQUE O ESPAÇO = PONTO {dot}      SEGURE O ESPAÇO = TRAÇO {dah}',
        'menu_begin': '[ENTER] COMEÇAR', 'menu_continue': '[C] CONTINUAR DO CAPÍTULO {n}',
        'menu_rest': '[P] PRATICAR   [L] IDIOMA   [Q] SAIR',
        'chapter_label': 'CAPÍTULO {n}', 'first_letters': 'SUAS PRIMEIRAS LETRAS', 'new_letters': 'LETRAS NOVAS',
        'review_letters': 'REVISÃO: SEM LETRAS NOVAS, MAIS PRÁTICA',
        'try_them': 'EXPERIMENTE ▸ ', 'enter_begin': '[ENTER] COMEÇAR',
        'chapter_help': 'TOQUE / SEGURE O ESPAÇO PARA PRATICAR   [TAB] OUVIR DE NOVO',
        'brief_line': 'CAPÍTULO {n} · {title}', 'code_word': 'PALAVRA-CÓDIGO:  {word}', 'ready': '[ENTER] PRONTO',
        'encode_help': 'TOQUE = PONTO •    SEGURE = TRAÇO ━    [TAB] DICA    [ESC] SAIR',
        'no_lamp': 'DAQUI EM DIANTE, SEM LUZ. ESCUTE.', 'no_tape': 'SEM FITA AGORA. OLHE A LUZ E ESCUTE.',
        'decode_help': 'DIGITE AS LETRAS QUE OUVIR    [TAB] REPETIR    [ESC] SAIR',
        'time_bonus': '+{bonus} BÔNUS DE TEMPO', 'lives_left': 'VIDAS RESTANTES: {n}. TENTE DE NOVO.',
        'no_lives': 'SEM VIDAS.', 'continue': '[ENTER] CONTINUAR',
        'practice': 'PRÁTICA',
        'free_help': 'TOQUE = PONTO  ·  SEGURE = TRAÇO  ·  [BKSP] APAGAR  ·  [ESC] VOLTAR',
        'over_big': 'SINAL PERDIDO', 'over_line': 'A TECLA SILENCIOU.',
        'final_score': 'PONTUAÇÃO FINAL {score:06d}', 'new_best': 'NOVO RECORDE',
        'over_continue': 'CONTINUE DO CAPÍTULO {n} NA TELA INICIAL.',
        'end_big': 'FIM DA ESCUTA',
    },
}

# 5x7 font, drawn with half blocks: one cell wide, half a cell tall per pixel.


def pretty(pattern):
    return ' '.join(DOT if e == '.' else DAH for e in pattern)


def unlocked(chapter):
    return ''.join(LEVELS[:chapter])


def focus_letters(chapter):
    """The letters a chapter drills: its new ones, or for a review chapter the two groups before it."""
    return LEVELS[chapter - 1] or ''.join([g for g in LEVELS[:chapter] if g][-2:])


def longest_word(chapter, mode):
    """Received words restart short each time an aid comes off, then grow a letter a chapter."""
    if mode == 'decode':
        aid_removed_at = max(c for c in (1, LAMP_ONLY_FROM, SOUND_ONLY_FROM) if c <= chapter)
        return min(7, 4 + chapter - aid_removed_at)
    return min(8, 4 + chapter // 3)


def pick_word(chapter, lang, mode):
    known = set(unlocked(chapter))
    new = set(focus_letters(chapter))
    pool = [w for w in WORDS[lang] if set(w) <= known and len(w) <= longest_word(chapter, mode)]
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


# --------------------------------------------------------------------- signal

SIG_HZ = 600


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


# --------------------------------------------------------------------- game

class MorseGame:
    def __init__(self, args, audio, releases):
        self.args, self.audio, self.releases = args, audio, releases
        self.save_path = save_file_path('morse')
        # earlier versions saved beside the script, then in a morse-code folder
        saved = load_save(self.save_path, os.path.join(user_data_dir(), 'morse-code', 'save.json'),
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), '.save.json'))
        self.hi, self.saved_chapter = saved.get('hi', 0), saved.get('chapter', 1)
        self.lang = saved.get('lang') if saved.get('lang') in LANGS else 'en'
        self.score = self.lives = self.combo = self.beat_no = 0
        self.chapter, self.mode, self.free_text, self.last_word = 1, 'encode', '', None
        self.msg_until = 0.0
        self.set_state('lang', time.monotonic())

    def store_progress(self):
        write_save(self.save_path, {'hi': self.hi, 'chapter': self.saved_chapter, 'lang': self.lang})

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
        self.audio.stop_signal_playback()
        self.set_state('title', now)

    def start_game(self, chapter, now):
        self.score, self.lives, self.combo, self.chapter, self.last_word = 0, 3, 0, chapter, None
        self.open_chapter(now)

    def open_chapter(self, now):
        if self.chapter > len(self.chapters):
            return self.finish(now)
        self.saved_chapter = max(self.saved_chapter, self.chapter)
        self.store_progress()
        self.beat_no, self.free_text = 0, ''
        self.new_letters = focus_letters(self.chapter)
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
        self.word = self.beat['word'] or (self.last_word if echo else pick_word(self.chapter, self.lang, self.mode))
        self.audio.stop_signal_playback()
        self.set_state('brief', now)

    def start_play(self, now):
        self.set_state('play', now)
        self.pos, self.hint = 0, self.chapter <= 3
        ch, n = self.chapter, len(self.word)
        if self.mode == 'decode':
            wpm, farnsworth = min(11 + ch * .5, 19), max(1.3, 3.4 - .12 * ch)
            self.on, sig_len = schedule(self.word, wpm, farnsworth)
            self.show_lamp, self.show_tape = ch < SOUND_ONLY_FROM, ch < LAMP_ONLY_FROM
            self.replay(now, lead=.8)
            budget = sig_len + .8 + n * max(2.5, 5 - .15 * ch)
        else:
            budget = n * max(3, 7 - .25 * ch)
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
        self.audio.stop_signal_playback()
        self.set_state('win', now)
        self.audio.play(notes([523, 659, 784], .12, .1), cut=True)

    def lose(self, now):
        self.p_end, self.lives, self.combo = 1.0, self.lives - 1, 0
        self.banner = random.choice(LOSE_BANNERS[self.lang])
        self.audio.stop_signal_playback()
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
        self.store_progress()

    def game_over(self, now):
        self.record_score()
        self.set_state('game_over', now)
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

    def on_key_press(self, k, now):
        s = self.state
        if k == 'ESC':
            if s in ('title', 'lang'):
                raise Eject
            return self.to_title(now)
        if k == ' ':  # a typed space: only sent when releases are unknown
            self.space_down(now)
            return
        enter = k in ('\r', '\n')
        if enter and s in ('chapter', 'brief', 'ending') and not self.typed_all:
            self.t_state -= 100  # skip the draw_typed_lines
            return
        if s == 'lang':
            if k in ('1', '2'):
                self.lang = LANGS[int(k) - 1]
            elif enter:
                self.store_progress()
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
                raise Eject
        elif s == 'chapter':
            if enter:
                self.open_beat(now)
            elif k == '\t':
                self.play_new_letters()
        elif s == 'brief' and enter:
            self.start_play(now)
        elif s in ('win', 'lose') and enter and now - self.t_state > 1.0:
            self.after_result(now)
        elif s in ('game_over', 'ending') and enter and now - self.t_state > 1.5:
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
        c = Canvas(width, height, PAPER, INK)
        if width < 80 or height < 24:
            c.ox = c.oy = 0
            c.put(0, 0, self.text('size'), AMBER)
            return c
        getattr(self, 'draw_' + self.state)(c, now)
        return c

    def draw_typed_lines(self, c, y, lines, now, col=PAPER):
        self.typed_all = draw_typed_lines(c, y, lines, now - self.t_state, col)
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
        sprite(c, tx, ty, tgt, PALETTE)
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
            sprite(c, mx, my, mov, PALETTE, flicker=int(now * 4) % 2)
        elif won_t < 1.5:
            sprite(c, mx, my, mov, PALETTE, faded=FAINT)

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
        self.draw_typed_lines(c, 8, chap['intro'], now)
        label = 'first_letters' if self.chapter == 1 else 'new_letters' if LEVELS[self.chapter - 1] else 'review_letters'
        c.center(12, self.text(label), TEAL)
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
        if self.draw_typed_lines(c, 14, [self.fmt(ln) for ln in self.beat['brief']] + ['', self.beat['task']], now):
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
        x0 = 40 - big_text_width(self.word) // 2
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
            if not self.show_lamp:
                c.center(20, self.text('no_lamp'), DIM)
            else:
                lit = any(s <= t < e for s, e, _, _ in self.on)
                c.put(2, 20, self.text('lamp'), INK if lit else DIM, LAMP if lit else FAINT)
            if self.show_lamp and not self.show_tape:
                c.put(10, 20, self.text('no_tape'), DIM)
            elif self.show_tape:
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

    def draw_game_over(self, c, now):
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
        if self.draw_typed_lines(c, 19, ENDING[self.lang], now, DIM):
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

def selftest():
    """Assert the keyers and the story data; raises AssertionError at the first problem."""
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
    assert all(ch in FONT for ch in MORSE)
    assert all(len(set(map(len, rows))) == 1 and set(''.join(rows)) <= set(PALETTE) | {'.'}
               for rows in SPRITES.values())
    for lang in LANGS:
        chapters = CHAPTERS[lang]
        assert len(chapters) == len(LEVELS) and set(UI[lang]) == set(UI['en'])
        assert all(set(w) <= set(MORSE) for w in WORDS[lang])
        for n, ch in enumerate(chapters, 1):
            for b in ch['beats']:
                assert not b['word'] or set(b['word']) <= set(unlocked(n)), (lang, n, b['word'])
                assert any(set(w) <= set(unlocked(n)) and len(w) <= longest_word(n, b['mode'])
                           for w in WORDS[lang]), (lang, n, b['mode'])
        assert all(len(ch['beats']) == 3 and big_text_width(ch['title']) <= 80 for ch in chapters)
        assert all(big_text_width(b) <= 80 for b in WIN_BANNERS[lang] + LOSE_BANNERS[lang])
        lines = ENDING[lang] + [ln for ch in chapters for ln in ch['intro']]
        for b in (b for ch in chapters for b in ch['beats']):
            assert b['scene'] in SCENES
            lines += [ln.format(word='W' * 8) for ln in b['brief']] + [b['task'], b['win'].format(word='W' * 8), b['lose'].format(word='W' * 8)]
        assert all(len(ln) <= 78 for ln in lines), [ln for ln in lines if len(ln) > 78]


def add_morse_arguments(parser):
    delay, interval = read_system_key_repeat()
    parser.add_argument('--repeat-delay', type=float, default=delay, help='keyboard autorepeat delay, seconds')
    parser.add_argument('--repeat-interval', type=float, default=interval, help='autorepeat interval, seconds')
    parser.add_argument('--letter-gap', type=float, default=.3, help='silence that ends a letter, seconds')
    parser.add_argument('--dah-time', type=float, default=.2,
                        help='with key releases reported: press at least this long for a dah, seconds')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(ap)
    add_morse_arguments(ap)
    args = ap.parse_args()
    if args.selftest:
        engine.selftest()
        selftest()
        return print('selftest ok')
    audio = Audio(args.volume)
    terminal = open_terminal(args)
    try:
        run(MorseGame(args, audio, terminal.reports_release), terminal)
    finally:
        audio.close()


if __name__ == '__main__':
    main()
