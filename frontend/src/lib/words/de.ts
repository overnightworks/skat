// Generated from the de catalog by design-catalogs. Do not edit.

export const language = "de";
const numberFormat = new Intl.NumberFormat("de");
const pluralRules = new Intl.PluralRules("de");
// prettier-ignore
export type Words = {
    readonly "app.name": string;
    readonly "app.reconnecting": string;
    readonly "app.unreachable": string;
    readonly "app.pageNotFound": string;
    readonly "app.pageFailed": string;
    readonly "account.title": string;
    readonly "start.newTable": string;
    readonly "start.seriesLength": string;
    readonly "start.seriesGames": (count: number) => string;
    readonly "start.seriesFewer": string;
    readonly "start.seriesMore": string;
    readonly "start.openTable": string;
    readonly "start.cancelNewTable": string;
    readonly "start.newTableFailed": string;
    readonly "start.visibility": string;
    readonly "start.visibilityOpen": string;
    readonly "start.visibilityPrivate": string;
    readonly "start.visibilityInfoButton": string;
    readonly "start.visibilityInfo": string;
    readonly "lobby.myTables": string;
    readonly "lobby.openTables": string;
    readonly "lobby.noOpenTables": string;
    readonly "lobby.openTable": (gaps: { readonly title: string }) => string;
    readonly "lobby.title": (gaps: { readonly name: string }) => string;
    readonly "lobby.titleSibilant": (gaps: { readonly name: string }) => string;
    readonly "lobby.titleNameless": string;
    readonly "lobby.progress": (gaps: { readonly count: number; readonly game: string }) => string;
    readonly "lobby.length": (count: number) => string;
    readonly "lobby.sideYou": string;
    readonly "lobby.seatFree": string;
    readonly "lobby.seatAway": string;
    readonly "lobby.minutesLeft": (count: number, gaps: { readonly minutes: string }) => string;
    readonly "lobby.ownSeatFreeIn": (count: number, gaps: { readonly minutes: string }) => string;
    readonly "lobby.otherSeatFreeIn": (count: number, gaps: { readonly minutes: string; readonly name: string }) => string;
    readonly "lobby.otherSeatFreeInSibilant": (count: number, gaps: { readonly minutes: string; readonly name: string }) => string;
    readonly "lobby.chipYourTurn": string;
    readonly "lobby.chipResultWaits": string;
    readonly "lobby.chipSeriesOver": string;
    readonly "lobby.private": string;
    readonly "lobby.sitAt": (gaps: { readonly title: string }) => string;
    readonly "lobby.sitFailed": string;
    readonly "lobby.chipGameWaits": string;
    readonly "lobby.chipPaused": string;
    readonly "lobby.endsInDays": (count: number, gaps: { readonly days: string }) => string;
    readonly "lobby.endsToday": string;
    readonly "table.waitingForPlayers": string;
    readonly "table.seatFree": string;
    readonly "table.seatAway": string;
    readonly "table.copyLink": string;
    readonly "table.linkCopied": string;
    readonly "table.linkCopyFailed": string;
    readonly "table.loadFailed": string;
    readonly "table.loadFailedHint": string;
    readonly "table.watchers": string;
    readonly "table.lobby": string;
    readonly "table.lobbyWaiting": (count: number) => string;
    readonly "table.reconnecting": string;
    readonly "table.sitDown": string;
    readonly "table.standUp": string;
    readonly "table.standUpArmed": string;
    readonly "table.seatTaken": string;
    readonly "table.commandFailed": string;
    readonly "table.bidding": string;
    readonly "table.pass": string;
    readonly "table.waitingFor": (gaps: { readonly names: string }) => string;
    readonly "table.wantsToGiveUp": (gaps: { readonly name: string }) => string;
    readonly "table.givesUp": (gaps: { readonly name: string }) => string;
    readonly "table.giveUp": string;
    readonly "table.giveUpSure": string;
    readonly "table.accept": string;
    readonly "table.playOn": string;
    readonly "table.saidNo": string;
    readonly "table.noAnswerYet": string;
    readonly "table.abort": string;
    readonly "table.abortSure": string;
    readonly "table.abortWait": string;
    readonly "table.wantsToAbort": (gaps: { readonly name: string }) => string;
    readonly "table.aborted": string;
    readonly "table.passedIn": string;
    readonly "table.gives": (gaps: { readonly name: string }) => string;
    readonly "table.waitsForYou": string;
    readonly "table.bidValue": (gaps: { readonly value: string }) => string;
    readonly "table.plays": string;
    readonly "table.playsValue": (gaps: { readonly name: string; readonly value: string }) => string;
    readonly "table.chooses": (gaps: { readonly name: string }) => string;
    readonly "table.discards": (gaps: { readonly name: string }) => string;
    readonly "table.ramsch": string;
    readonly "table.pushCount": (gaps: { readonly count: number }) => string;
    readonly "table.pushFactor": (gaps: { readonly factor: string }) => string;
    readonly "table.push": string;
    readonly "table.thinks": string;
    readonly "table.nudge": string;
    readonly "table.nudged": string;
    readonly "table.nudgesYou": string;
    readonly "table.dealer": string;
    readonly "table.cardCount": string;
    readonly "table.open": string;
    readonly "table.openForAll": string;
    readonly "table.sideYou": string;
    readonly "table.weiter": string;
    readonly "table.seriesCount": (gaps: { readonly count: number; readonly game: string }) => string;
    readonly "table.seriesList": string;
    readonly "table.seriesListTitle": string;
    readonly "table.seriesListEmpty": string;
    readonly "table.seriesListFailed": string;
    readonly "table.seriesEnded": string;
    readonly "table.seriesGames": (count: number) => string;
    readonly "table.seriesRecord": (gaps: { readonly lost: string; readonly won: string }) => string;
    readonly "table.seriesGone": string;
    readonly "table.seriesNameless": string;
    readonly "table.seriesRamschOf": (gaps: { readonly name: string }) => string;
    readonly "table.seriesPushed": (gaps: { readonly count: number }) => string;
    readonly "table.newSeries": string;
    readonly "table.wantsToEndSeries": (gaps: { readonly name: string }) => string;
    readonly "table.endSeries": string;
    readonly "table.endSeriesSure": string;
    readonly "table.yes": string;
    readonly "table.no": string;
    readonly "table.watchingOnly": string;
    readonly "table.readyMark": string;
    readonly "table.notReadyMark": string;
    readonly "result.seatFree": string;
    readonly "result.hand": string;
    readonly "result.levelSpiel": string;
    readonly "result.levelSchneider": string;
    readonly "result.levelSchwarz": string;
    readonly "result.levelOuvert": string;
    readonly "result.matadorsWith": (count: number) => string;
    readonly "result.matadorsWithout": (count: number) => string;
    readonly "result.listGame": (gaps: { readonly score: string }) => string;
    readonly "result.listGameWord": (gaps: { readonly score: string; readonly word: string }) => string;
    readonly "result.wordKontra": string;
    readonly "result.wordRe": string;
    readonly "result.wordSupra": string;
    readonly "result.wordHirsch": string;
    readonly "result.wordFactor": (gaps: { readonly factor: string; readonly word: string }) => string;
    readonly "result.listBonus": (gaps: { readonly bonus: string }) => string;
    readonly "result.share": (gaps: { readonly gain: string; readonly opponents: string }) => string;
    readonly "result.announcedSchneider": string;
    readonly "result.announcedSchwarz": string;
    readonly "result.sideThem": string;
    readonly "result.trickPoints": string;
    readonly "result.sideYou": string;
    readonly "result.won": string;
    readonly "result.lost": string;
    readonly "result.overbid": string;
    readonly "result.givenUp": string;
    readonly "result.declarerWins": (gaps: { readonly name: string }) => string;
    readonly "result.declarerLoses": (gaps: { readonly name: string }) => string;
    readonly "result.opponentGameLine": (gaps: { readonly declarer: string; readonly game: string }) => string;
    readonly "result.missedSchneider": string;
    readonly "result.missedSchwarz": string;
    readonly "result.raise": (gaps: { readonly bid: string; readonly settled: string; readonly value: string }) => string;
    readonly "bock.factor": (gaps: { readonly factor: string }) => string;
    readonly "bock.plaque": (gaps: { readonly factor: string }) => readonly (string | { readonly marker: "factor"; readonly text: string })[];
    readonly "rules.chipBock": string;
    readonly "rules.bockLeft": (gaps: { readonly count: number }) => string;
    readonly "result.sidePoints": (gaps: { readonly points: string; readonly side: string }) => readonly (string | { readonly marker: "side" | "tally"; readonly text: string })[];
    readonly "result.eyes": (gaps: { readonly points: string }) => string;
    readonly "result.eyeCount": (gaps: { readonly name: string; readonly points: string }) => string;
    readonly "result.loses": (gaps: { readonly name: string }) => string;
    readonly "result.losesTogether": (gaps: { readonly names: string }) => string;
    readonly "result.byTen": string;
    readonly "result.jungfrau": string;
    readonly "result.durchmarsch": string;
    readonly "push.times": (gaps: { readonly count: number; readonly factor: string }) => string;
    readonly "push.timesFlat": (gaps: { readonly count: number }) => string;
    readonly "closed.notFound": string;
    readonly "closed.emptySeconds": (count: number) => string;
    readonly "closed.emptyMinutes": (count: number, gaps: { readonly minutes: string }) => string;
    readonly "closed.unplayedDays": (count: number) => string;
    readonly "closed.closed": string;
    readonly "closed.closedBy": (gaps: { readonly name: string }) => string;
    readonly "declare.commandFailed": string;
    readonly "declare.takeSkat": string;
    readonly "push.takeSkat": string;
    readonly "push.grandHand": string;
    readonly "push.grandHandAsk": string;
    readonly "declare.putBack": string;
    readonly "declare.announceGame": string;
    readonly "declare.hand": string;
    readonly "declare.levelSchneider": string;
    readonly "declare.levelSchwarz": string;
    readonly "declare.levelOuvert": string;
    readonly "play.commandFailed": string;
    readonly "play.swipeHint": string;
    readonly "play.sideUs": string;
    readonly "play.sideThem": string;
    readonly "play.trick": string;
    readonly "play.lastTrick": string;
    readonly "play.sideYou": string;
    readonly "kontra.kontra": string;
    readonly "kontra.re": string;
    readonly "kontra.supra": string;
    readonly "kontra.hirsch": string;
    readonly "kontra.plaque": (gaps: { readonly factor: string; readonly word: string }) => readonly (string | { readonly marker: "factor"; readonly text: string })[];
    readonly "kontra.stamp": (gaps: { readonly word: string }) => string;
    readonly "kontra.saidBy": (gaps: { readonly name: string; readonly word: string }) => string;
    readonly "kontra.commandFailed": string;
    readonly "kontra.decline": (gaps: { readonly word: string }) => string;
    readonly "kontra.firstCardWaits": (gaps: { readonly names: string }) => string;
    readonly "kontra.you": string;
    readonly "bid.hold": string;
    readonly "bid.pass": string;
    readonly "voice.pass": string;
    readonly "voice.kontra": string;
    readonly "voice.re": string;
    readonly "voice.supra": string;
    readonly "voice.hirsch": string;
    readonly "voice.value18": string;
    readonly "voice.value20": string;
    readonly "voice.value22": string;
    readonly "voice.value23": string;
    readonly "voice.value24": string;
    readonly "voice.value27": string;
    readonly "voice.value30": string;
    readonly "voice.value33": string;
    readonly "voice.value35": string;
    readonly "voice.value36": string;
    readonly "voice.value40": string;
    readonly "voice.value44": string;
    readonly "voice.value45": string;
    readonly "voice.value46": string;
    readonly "voice.value48": string;
    readonly "voice.value50": string;
    readonly "voice.value54": string;
    readonly "voice.value55": string;
    readonly "voice.value59": string;
    readonly "voice.value60": string;
    readonly "voice.value63": string;
    readonly "voice.value66": string;
    readonly "voice.value70": string;
    readonly "voice.value72": string;
    readonly "voice.value77": string;
    readonly "voice.value80": string;
    readonly "voice.value81": string;
    readonly "voice.value84": string;
    readonly "voice.value88": string;
    readonly "voice.value90": string;
    readonly "voice.value96": string;
    readonly "voice.value99": string;
    readonly "voice.value100": string;
    readonly "voice.value108": string;
    readonly "voice.value110": string;
    readonly "voice.value117": string;
    readonly "voice.value120": string;
    readonly "voice.value121": string;
    readonly "voice.value126": string;
    readonly "voice.value130": string;
    readonly "voice.value132": string;
    readonly "voice.value135": string;
    readonly "voice.value140": string;
    readonly "voice.value143": string;
    readonly "voice.value144": string;
    readonly "voice.value150": string;
    readonly "voice.value153": string;
    readonly "voice.value154": string;
    readonly "voice.value156": string;
    readonly "voice.value160": string;
    readonly "voice.value162": string;
    readonly "voice.value165": string;
    readonly "voice.value168": string;
    readonly "voice.value170": string;
    readonly "voice.value176": string;
    readonly "voice.value180": string;
    readonly "voice.value187": string;
    readonly "voice.value192": string;
    readonly "voice.value198": string;
    readonly "voice.value204": string;
    readonly "voice.value216": string;
    readonly "voice.value240": string;
    readonly "voice.value264": string;
    readonly "game.forehand": string;
    readonly "game.middlehand": string;
    readonly "game.rearhand": string;
    readonly "game.handName": (gaps: { readonly game: string }) => string;
    readonly "game.announcedSchneider": string;
    readonly "game.announcedSchwarz": string;
    readonly "game.ouvertName": (gaps: { readonly game: string }) => string;
    readonly "game.ouvertHandName": (gaps: { readonly game: string }) => string;
    readonly "game.karo": string;
    readonly "game.herz": string;
    readonly "game.pik": string;
    readonly "game.kreuz": string;
    readonly "game.grand": string;
    readonly "game.null": string;
    readonly "game.ramsch": string;
    readonly "game.rankSeven": string;
    readonly "game.rankEight": string;
    readonly "game.rankNine": string;
    readonly "game.rankTen": string;
    readonly "game.rankJack": string;
    readonly "game.rankQueen": string;
    readonly "game.rankKing": string;
    readonly "game.rankAce": string;
    readonly "game.cardName": (gaps: { readonly rank: string; readonly suit: string }) => string;
    readonly "legal.imprint": string;
    readonly "legal.privacy": string;
    readonly "legal.terms": string;
    readonly "sound.panelName": string;
    readonly "sound.muted": string;
    readonly "sound.on": string;
    readonly "sound.tone": string;
    readonly "sound.volume": string;
    readonly "sound.sets": string;
    readonly "sound.voice": string;
    readonly "sound.motion": string;
    readonly "sound.replayMotion": string;
    readonly "sound.reducedMotionNote": string;
    readonly "sound.playsOnce": string;
    readonly "sound.more": string;
    readonly "sound.setLeise": string;
    readonly "sound.setStammtisch": string;
    readonly "sound.setFunkeln": string;
    readonly "sound.lastTrick": string;
    readonly "sound.lastTrickSweep": string;
    readonly "sound.lastTrickStay": string;
    readonly "sound.motionDezent": string;
    readonly "sound.motionVerspielt": string;
    readonly "card.letterJack": string;
    readonly "card.letterQueen": string;
    readonly "card.letterKing": string;
    readonly "card.letterAce": string;
    readonly "agents.pill": string;
    readonly "table.agentSits": (gaps: { readonly name: string }) => string;
    readonly "table.agentLeft": (gaps: { readonly name: string }) => string;
    readonly "table.standUpNotice": (gaps: { readonly name: string }) => string;
    readonly "table.chairLocked": string;
    readonly "table.playsOn": (gaps: { readonly name: string }) => string;
    readonly "table.playingOn": (gaps: { readonly names: string }) => string;
    readonly "table.sitQuestion": string;
    readonly "table.sitQuestionCancel": string;
    readonly "table.close": string;
    readonly "table.closeQuestion": string;
    readonly "table.closeConfirm": string;
    readonly "table.closeCancel": string;
    readonly "table.takeOverNamed": (gaps: { readonly name: string }) => string;
    readonly "table.takeOverApostrophe": (gaps: { readonly name: string }) => string;
    readonly "table.takeOverUnnamed": string;
    readonly "logout.button": string;
    readonly "start.rulePoints": string;
    readonly "start.rulePointsLine": string;
    readonly "start.ruleSets": string;
    readonly "start.setOfficial": string;
    readonly "start.setsUnreadable": string;
    readonly "start.saveRules": string;
    readonly "start.saveName": string;
    readonly "start.savedNameWith": (gaps: { readonly rules: string; readonly set: string }) => string;
    readonly "start.savedNameAdjusted": (gaps: { readonly set: string }) => string;
    readonly "start.saveNameTaken": string;
    readonly "start.saveFailed": string;
    readonly "start.ruleKontra": string;
    readonly "start.ruleKontraLine": string;
    readonly "start.ruleRamsch": string;
    readonly "start.ruleRamschLine": string;
    readonly "start.rulePushing": string;
    readonly "start.rulePushingLine": string;
    readonly "start.ruleBock": string;
    readonly "start.ruleBockLine": string;
    readonly "start.askKontraSayer": string;
    readonly "start.pillAnyOpponent": string;
    readonly "start.pillBiddersOnly": string;
    readonly "start.askKontraReach": string;
    readonly "start.pillKontraRe": string;
    readonly "start.pillKontraReStandings": string;
    readonly "start.pillUpToHirsch": string;
    readonly "start.askRamschScoring": string;
    readonly "start.pillScoringPoints": string;
    readonly "start.pillScoringPointsByTen": string;
    readonly "start.pillScoringSkatToLoser": string;
    readonly "start.askJungfrau": string;
    readonly "start.pillJungfrauDoublesLoser": string;
    readonly "start.pillJungfrauOff": string;
    readonly "start.askDurchmarsch": string;
    readonly "start.pillDurchmarschWins120": string;
    readonly "start.pillDurchmarschWins120Flat": string;
    readonly "start.pillDurchmarschOff": string;
    readonly "start.askPushingRule": string;
    readonly "start.pillPushingJacksStay": string;
    readonly "start.pillPushingJacksMayGo": string;
    readonly "start.pillPushingNoDoubling": string;
    readonly "start.askGrandHand": string;
    readonly "start.pillGrandHandOff": string;
    readonly "start.pillGrandHandAllowed": string;
    readonly "start.askBockTriggers": string;
    readonly "start.flagSixtySixty": string;
    readonly "start.flagWonGrandHand": string;
    readonly "start.flagLostAfterKontra": string;
    readonly "start.flagRe": string;
    readonly "start.flagPassedIn": string;
    readonly "start.flagSchneider": string;
    readonly "start.askBockOverlap": string;
    readonly "start.pillOverlapAppend": string;
    readonly "start.pillOverlapMultiply": string;
    readonly "start.pillOverlapIgnore": string;
    readonly "rules.button": string;
    readonly "rules.title": string;
    readonly "rules.lockBadge": string;
    readonly "rules.lockInfo": string;
    readonly "rules.info": string;
    readonly "rules.close": string;
    readonly "rules.chipOfficial": string;
    readonly "rules.chipPoints": string;
    readonly "rules.chipKontra": string;
    readonly "rules.chipRamsch": string;
    readonly "rules.namePoints": string;
    readonly "rules.nameKontra": string;
    readonly "rules.nameRamsch": string;
    readonly "rules.nameRamschBockRounds": string;
    readonly "rules.nameRamschPassedInAndBockRounds": string;
    readonly "rules.namePushing": string;
    readonly "rules.nameBock": string;
    readonly "rules.pointsFromTricks": string;
    readonly "rules.kontraSayerAnyOpponent": string;
    readonly "rules.kontraSayerBiddersOnly": string;
    readonly "rules.kontraReachKontraRe": string;
    readonly "rules.kontraReachKontraReStandings": string;
    readonly "rules.kontraReachUpToHirsch": string;
    readonly "rules.kontraDeadlineOwnCard": string;
    readonly "rules.kontraDeadlineFirstCard": string;
    readonly "rules.ramschScoringPoints": string;
    readonly "rules.ramschScoringPointsByTen": string;
    readonly "rules.ramschScoringSkatToLoser": string;
    readonly "rules.jungfrauDoublesLoser": string;
    readonly "rules.jungfrauOff": string;
    readonly "rules.durchmarschWins120": string;
    readonly "rules.durchmarschWins120Flat": string;
    readonly "rules.durchmarschOff": string;
    readonly "rules.pushingJacksStay": string;
    readonly "rules.pushingJacksMayGo": string;
    readonly "rules.pushingNoDoubling": string;
    readonly "rules.grandHandAllowed": string;
    readonly "rules.bockTriggers": (gaps: { readonly triggers: string }) => string;
    readonly "rules.bockTriggerSixtySixty": string;
    readonly "rules.bockTriggerWonGrandHand": string;
    readonly "rules.bockTriggerLostAfterKontra": string;
    readonly "rules.bockTriggerRe": string;
    readonly "rules.bockTriggerPassedIn": string;
    readonly "rules.bockTriggerSchneider": string;
    readonly "rules.bockTriggerSchwarz": string;
    readonly "rules.bockTriggerTotalEndingIn00": string;
    readonly "rules.bockOverlapAppend": string;
    readonly "rules.bockOverlapMultiply": string;
    readonly "rules.bockOverlapIgnore": string;
};
// prettier-ignore
export const words: Words = {
    "app.name": "Skat",
    "app.reconnecting": "verbinde neu",
    "app.unreachable": "Skat ist gerade nicht erreichbar.",
    "app.pageNotFound": "Diese Seite gibt es nicht.",
    "app.pageFailed": "Diese Seite lässt sich nicht laden.",
    "account.title": "Konto",
    "start.newTable": "Neuer Tisch",
    "start.seriesLength": "Länge der Serie",
    "start.seriesGames": (count: number) => ({
        zero: "Spiele",
        one: "Spiel",
        two: "Spiele",
        few: "Spiele",
        many: "Spiele",
        other: "Spiele",
    })[pluralRules.select(count)],
    "start.seriesFewer": "3 Spiele weniger",
    "start.seriesMore": "3 Spiele mehr",
    "start.openTable": "Aufmachen",
    "start.cancelNewTable": "Abbrechen",
    "start.newTableFailed": "Der Tisch konnte nicht eröffnet werden.",
    "start.visibility": "Wer den Tisch sieht",
    "start.visibilityOpen": "Offen",
    "start.visibilityPrivate": "Privat",
    "start.visibilityInfoButton": "Info",
    "start.visibilityInfo": "Offen: steht in der Lobby. Privat: nur mit dem Link.",
    "lobby.myTables": "Meine Tische",
    "lobby.openTables": "Offene Tische",
    "lobby.noOpenTables": "Sonst ist kein Tisch offen",
    "lobby.openTable": (gaps: { readonly title: string }) => gaps.title + " öffnen",
    "lobby.title": (gaps: { readonly name: string }) => gaps.name + "s Tisch",
    "lobby.titleSibilant": (gaps: { readonly name: string }) => gaps.name + "' Tisch",
    "lobby.titleNameless": "Tisch",
    "lobby.progress": (gaps: { readonly count: number; readonly game: string }) => "Spiel " + gaps.game + " von " + numberFormat.format(gaps.count),
    "lobby.length": (count: number) => ({
        zero: numberFormat.format(count) + " Spiele",
        one: numberFormat.format(count) + " Spiel",
        two: numberFormat.format(count) + " Spiele",
        few: numberFormat.format(count) + " Spiele",
        many: numberFormat.format(count) + " Spiele",
        other: numberFormat.format(count) + " Spiele",
    })[pluralRules.select(count)],
    "lobby.sideYou": "Du",
    "lobby.seatFree": "Frei",
    "lobby.seatAway": "nicht da",
    "lobby.minutesLeft": (count: number, gaps: { readonly minutes: string }) => ({
        zero: "noch " + gaps.minutes + " Min",
        one: "noch " + gaps.minutes + " Min",
        two: "noch " + gaps.minutes + " Min",
        few: "noch " + gaps.minutes + " Min",
        many: "noch " + gaps.minutes + " Min",
        other: "noch " + gaps.minutes + " Min",
    })[pluralRules.select(count)],
    "lobby.ownSeatFreeIn": (count: number, gaps: { readonly minutes: string }) => ({
        zero: "Dein Platz wird in " + gaps.minutes + " Minuten frei",
        one: "Dein Platz wird in " + gaps.minutes + " Minute frei",
        two: "Dein Platz wird in " + gaps.minutes + " Minuten frei",
        few: "Dein Platz wird in " + gaps.minutes + " Minuten frei",
        many: "Dein Platz wird in " + gaps.minutes + " Minuten frei",
        other: "Dein Platz wird in " + gaps.minutes + " Minuten frei",
    })[pluralRules.select(count)],
    "lobby.otherSeatFreeIn": (count: number, gaps: { readonly minutes: string; readonly name: string }) => ({
        zero: gaps.name + "s Platz wird in " + gaps.minutes + " Minuten frei",
        one: gaps.name + "s Platz wird in " + gaps.minutes + " Minute frei",
        two: gaps.name + "s Platz wird in " + gaps.minutes + " Minuten frei",
        few: gaps.name + "s Platz wird in " + gaps.minutes + " Minuten frei",
        many: gaps.name + "s Platz wird in " + gaps.minutes + " Minuten frei",
        other: gaps.name + "s Platz wird in " + gaps.minutes + " Minuten frei",
    })[pluralRules.select(count)],
    "lobby.otherSeatFreeInSibilant": (count: number, gaps: { readonly minutes: string; readonly name: string }) => ({
        zero: gaps.name + "' Platz wird in " + gaps.minutes + " Minuten frei",
        one: gaps.name + "' Platz wird in " + gaps.minutes + " Minute frei",
        two: gaps.name + "' Platz wird in " + gaps.minutes + " Minuten frei",
        few: gaps.name + "' Platz wird in " + gaps.minutes + " Minuten frei",
        many: gaps.name + "' Platz wird in " + gaps.minutes + " Minuten frei",
        other: gaps.name + "' Platz wird in " + gaps.minutes + " Minuten frei",
    })[pluralRules.select(count)],
    "lobby.chipYourTurn": "Du bist dran",
    "lobby.chipResultWaits": "Ergebnis wartet",
    "lobby.chipSeriesOver": "Serie vorbei",
    "lobby.private": "Privat",
    "lobby.sitAt": (gaps: { readonly title: string }) => gaps.title + ": hinsetzen",
    "lobby.sitFailed": "Das Hinsetzen hat nicht geklappt",
    "lobby.chipGameWaits": "Spiel wartet",
    "lobby.chipPaused": "pausiert",
    "lobby.endsInDays": (count: number, gaps: { readonly days: string }) => ({
        zero: "endet in " + gaps.days + " Tagen",
        one: "endet in " + gaps.days + " Tag",
        two: "endet in " + gaps.days + " Tagen",
        few: "endet in " + gaps.days + " Tagen",
        many: "endet in " + gaps.days + " Tagen",
        other: "endet in " + gaps.days + " Tagen",
    })[pluralRules.select(count)],
    "lobby.endsToday": "endet heute",
    "table.waitingForPlayers": "Warte auf Mitspieler",
    "table.seatFree": "Frei",
    "table.seatAway": "nicht da",
    "table.copyLink": "Link kopieren",
    "table.linkCopied": "Link kopiert",
    "table.linkCopyFailed": "Der Link ließ sich nicht kopieren",
    "table.loadFailed": "Der Tisch lässt sich gerade nicht laden",
    "table.loadFailedHint": "Lade die Seite neu, um es noch einmal zu versuchen.",
    "table.watchers": "Zuschauer",
    "table.lobby": "Lobby",
    "table.lobbyWaiting": (count: number) => ({
        zero: "Lobby, " + numberFormat.format(count) + " Tische warten auf dich",
        one: "Lobby, " + numberFormat.format(count) + " Tisch wartet auf dich",
        two: "Lobby, " + numberFormat.format(count) + " Tische warten auf dich",
        few: "Lobby, " + numberFormat.format(count) + " Tische warten auf dich",
        many: "Lobby, " + numberFormat.format(count) + " Tische warten auf dich",
        other: "Lobby, " + numberFormat.format(count) + " Tische warten auf dich",
    })[pluralRules.select(count)],
    "table.reconnecting": "verbinde neu",
    "table.sitDown": "Hinsetzen",
    "table.standUp": "Aufstehen",
    "table.standUpArmed": "Wirklich aufstehen?",
    "table.seatTaken": "Platz vergeben",
    "table.commandFailed": "Das hat nicht geklappt",
    "table.bidding": "Reizen",
    "table.pass": "Weg",
    "table.waitingFor": (gaps: { readonly names: string }) => "Warte auf " + gaps.names,
    "table.wantsToGiveUp": (gaps: { readonly name: string }) => gaps.name + " will aufgeben",
    "table.givesUp": (gaps: { readonly name: string }) => gaps.name + " gibt auf",
    "table.giveUp": "Aufgeben",
    "table.giveUpSure": "Wirklich aufgeben?",
    "table.accept": "Annehmen",
    "table.playOn": "Weiterspielen",
    "table.saidNo": "sagte Nein",
    "table.noAnswerYet": "noch keine Antwort",
    "table.abort": "Abbrechen",
    "table.abortSure": "Wirklich abbrechen?",
    "table.abortWait": "Warten",
    "table.wantsToAbort": (gaps: { readonly name: string }) => gaps.name + " will abbrechen",
    "table.aborted": "Spiel abgebrochen",
    "table.passedIn": "Eingepasst",
    "table.gives": (gaps: { readonly name: string }) => gaps.name + " gibt",
    "table.waitsForYou": "wartet auf dich",
    "table.bidValue": (gaps: { readonly value: string }) => "Reizwert " + gaps.value,
    "table.plays": "spielt",
    "table.playsValue": (gaps: { readonly name: string; readonly value: string }) => gaps.name + " spielt, " + gaps.value,
    "table.chooses": (gaps: { readonly name: string }) => gaps.name + " wählt",
    "table.discards": (gaps: { readonly name: string }) => gaps.name + " drückt",
    "table.ramsch": "Ramsch",
    "table.pushCount": (gaps: { readonly count: number }) => numberFormat.format(gaps.count) + "× geschoben",
    "table.pushFactor": (gaps: { readonly factor: string }) => "×" + gaps.factor,
    "table.push": "Schieben",
    "table.thinks": "denkt",
    "table.nudge": "anstupsen",
    "table.nudged": "Angestupst",
    "table.nudgesYou": "stupst dich an",
    "table.dealer": "Geber",
    "table.cardCount": "Karten",
    "table.open": "Offen",
    "table.openForAll": "Offen für alle",
    "table.sideYou": "Du",
    "table.weiter": "Weiter",
    "table.seriesCount": (gaps: { readonly count: number; readonly game: string }) => "Spiel " + gaps.game + " von " + numberFormat.format(gaps.count),
    "table.seriesList": "Liste der Spiele",
    "table.seriesListTitle": "Spiele",
    "table.seriesListEmpty": "Noch kein Spiel gespielt",
    "table.seriesListFailed": "Die Liste lässt sich nicht laden.",
    "table.seriesEnded": "Serie zu Ende",
    "table.seriesGames": (count: number) => ({
        zero: numberFormat.format(count) + " Spiele",
        one: numberFormat.format(count) + " Spiel",
        two: numberFormat.format(count) + " Spiele",
        few: numberFormat.format(count) + " Spiele",
        many: numberFormat.format(count) + " Spiele",
        other: numberFormat.format(count) + " Spiele",
    })[pluralRules.select(count)],
    "table.seriesRecord": (gaps: { readonly lost: string; readonly won: string }) => gaps.won + " gewonnen · " + gaps.lost + " verloren",
    "table.seriesGone": "gegangen",
    "table.seriesNameless": "Jemand",
    "table.seriesRamschOf": (gaps: { readonly name: string }) => "Ramsch, " + gaps.name,
    "table.seriesPushed": (gaps: { readonly count: number }) => numberFormat.format(gaps.count) + "× geschoben",
    "table.newSeries": "Neue Serie",
    "table.wantsToEndSeries": (gaps: { readonly name: string }) => gaps.name + " will die Serie beenden",
    "table.endSeries": "Serie beenden",
    "table.endSeriesSure": "Wirklich beenden?",
    "table.yes": "Ja",
    "table.no": "Nein",
    "table.watchingOnly": "Du schaust zu",
    "table.readyMark": "Weiter getippt",
    "table.notReadyMark": "noch nicht getippt",
    "result.seatFree": "Frei",
    "result.hand": "Hand",
    "result.levelSpiel": "Spiel",
    "result.levelSchneider": "Schneider",
    "result.levelSchwarz": "Schwarz",
    "result.levelOuvert": "Ouvert",
    "result.matadorsWith": (count: number) => ({
        zero: "mit " + numberFormat.format(count),
        one: "mit " + numberFormat.format(count),
        two: "mit " + numberFormat.format(count),
        few: "mit " + numberFormat.format(count),
        many: "mit " + numberFormat.format(count),
        other: "mit " + numberFormat.format(count),
    })[pluralRules.select(count)],
    "result.matadorsWithout": (count: number) => ({
        zero: "ohne " + numberFormat.format(count),
        one: "ohne " + numberFormat.format(count),
        two: "ohne " + numberFormat.format(count),
        few: "ohne " + numberFormat.format(count),
        many: "ohne " + numberFormat.format(count),
        other: "ohne " + numberFormat.format(count),
    })[pluralRules.select(count)],
    "result.listGame": (gaps: { readonly score: string }) => "Spiel " + gaps.score,
    "result.listGameWord": (gaps: { readonly score: string; readonly word: string }) => "Spiel · " + gaps.word + " " + gaps.score,
    "result.wordKontra": "Kontra",
    "result.wordRe": "Re",
    "result.wordSupra": "Supra",
    "result.wordHirsch": "Hirsch",
    "result.wordFactor": (gaps: { readonly factor: string; readonly word: string }) => gaps.word + " ×" + gaps.factor,
    "result.listBonus": (gaps: { readonly bonus: string }) => "Liste " + gaps.bonus,
    "result.share": (gaps: { readonly gain: string; readonly opponents: string }) => "· " + gaps.opponents + " je " + gaps.gain,
    "result.announcedSchneider": "Schneider angesagt",
    "result.announcedSchwarz": "Schwarz angesagt",
    "result.sideThem": "Gegner",
    "result.trickPoints": "Augen",
    "result.sideYou": "Du",
    "result.won": "Gewonnen!",
    "result.lost": "Verloren",
    "result.overbid": "Überreizt",
    "result.givenUp": "Aufgegeben",
    "result.declarerWins": (gaps: { readonly name: string }) => gaps.name + " gewinnt",
    "result.declarerLoses": (gaps: { readonly name: string }) => gaps.name + " verliert",
    "result.opponentGameLine": (gaps: { readonly declarer: string; readonly game: string }) => gaps.declarer + ", " + gaps.game,
    "result.missedSchneider": "Schneider angesagt, nicht erreicht",
    "result.missedSchwarz": "Schwarz angesagt, nicht erreicht",
    "result.raise": (gaps: { readonly bid: string; readonly settled: string; readonly value: string }) => "Wert " + gaps.value + " < Reizwert " + gaps.bid + " → " + gaps.settled,
    "bock.factor": (gaps: { readonly factor: string }) => "Bock ×" + gaps.factor,
    "bock.plaque": (gaps: { readonly factor: string }): readonly (string | { readonly marker: "factor"; readonly text: string })[] => ["Bock ", { marker: "factor", text: "×" + gaps.factor }],
    "rules.chipBock": "Bock",
    "rules.bockLeft": (gaps: { readonly count: number }) => "noch " + numberFormat.format(gaps.count),
    "result.sidePoints": (gaps: { readonly points: string; readonly side: string }): readonly (string | { readonly marker: "side" | "tally"; readonly text: string })[] => [{ marker: "side", text: gaps.side }, " ", { marker: "tally", text: gaps.points }],
    "result.eyes": (gaps: { readonly points: string }) => gaps.points + " Augen",
    "result.eyeCount": (gaps: { readonly name: string; readonly points: string }) => gaps.name + " " + gaps.points,
    "result.loses": (gaps: { readonly name: string }) => gaps.name + " verliert",
    "result.losesTogether": (gaps: { readonly names: string }) => gaps.names + " verlieren",
    "result.byTen": "÷ 10",
    "result.jungfrau": "Jungfrau ×2",
    "result.durchmarsch": "Durchmarsch",
    "push.times": (gaps: { readonly count: number; readonly factor: string }) => numberFormat.format(gaps.count) + "× geschoben ×" + gaps.factor,
    "push.timesFlat": (gaps: { readonly count: number }) => numberFormat.format(gaps.count) + "× geschoben",
    "closed.notFound": "Tisch nicht gefunden",
    "closed.emptySeconds": (count: number) => ({
        zero: numberFormat.format(count) + " Sekunden niemand da: Tisch geschlossen",
        one: numberFormat.format(count) + " Sekunde niemand da: Tisch geschlossen",
        two: numberFormat.format(count) + " Sekunden niemand da: Tisch geschlossen",
        few: numberFormat.format(count) + " Sekunden niemand da: Tisch geschlossen",
        many: numberFormat.format(count) + " Sekunden niemand da: Tisch geschlossen",
        other: numberFormat.format(count) + " Sekunden niemand da: Tisch geschlossen",
    })[pluralRules.select(count)],
    "closed.emptyMinutes": (count: number, gaps: { readonly minutes: string }) => ({
        zero: gaps.minutes + " Minuten niemand da: Tisch geschlossen",
        one: gaps.minutes + " Minute niemand da: Tisch geschlossen",
        two: gaps.minutes + " Minuten niemand da: Tisch geschlossen",
        few: gaps.minutes + " Minuten niemand da: Tisch geschlossen",
        many: gaps.minutes + " Minuten niemand da: Tisch geschlossen",
        other: gaps.minutes + " Minuten niemand da: Tisch geschlossen",
    })[pluralRules.select(count)],
    "closed.unplayedDays": (count: number) => ({
        zero: numberFormat.format(count) + " Tage nicht gespielt: Tisch geschlossen",
        one: numberFormat.format(count) + " Tag nicht gespielt: Tisch geschlossen",
        two: numberFormat.format(count) + " Tage nicht gespielt: Tisch geschlossen",
        few: numberFormat.format(count) + " Tage nicht gespielt: Tisch geschlossen",
        many: numberFormat.format(count) + " Tage nicht gespielt: Tisch geschlossen",
        other: numberFormat.format(count) + " Tage nicht gespielt: Tisch geschlossen",
    })[pluralRules.select(count)],
    "closed.closed": "Tisch geschlossen",
    "closed.closedBy": (gaps: { readonly name: string }) => gaps.name + " hat den Tisch geschlossen",
    "declare.commandFailed": "Das hat nicht geklappt",
    "declare.takeSkat": "Aufnehmen",
    "push.takeSkat": "Skat nehmen",
    "push.grandHand": "Grand Hand",
    "push.grandHandAsk": "Grand Hand?",
    "declare.putBack": "Drücken",
    "declare.announceGame": "Ansagen",
    "declare.hand": "Hand",
    "declare.levelSchneider": "Schneider",
    "declare.levelSchwarz": "Schwarz",
    "declare.levelOuvert": "Ouvert",
    "play.commandFailed": "Das hat nicht geklappt",
    "play.swipeHint": "Nochmal tippen oder hochwischen spielt die Karte",
    "play.sideUs": "Wir",
    "play.sideThem": "Gegner",
    "play.trick": "Stich",
    "play.lastTrick": "Letzter Stich",
    "play.sideYou": "Du",
    "kontra.kontra": "Kontra",
    "kontra.re": "Re",
    "kontra.supra": "Supra",
    "kontra.hirsch": "Hirsch",
    "kontra.plaque": (gaps: { readonly factor: string; readonly word: string }): readonly (string | { readonly marker: "factor"; readonly text: string })[] => [gaps.word + " ", { marker: "factor", text: "×" + gaps.factor }],
    "kontra.stamp": (gaps: { readonly word: string }) => gaps.word + "!",
    "kontra.saidBy": (gaps: { readonly name: string; readonly word: string }) => gaps.name + " sagt " + gaps.word,
    "kontra.commandFailed": "Das hat nicht geklappt",
    "kontra.decline": (gaps: { readonly word: string }) => "Kein " + gaps.word,
    "kontra.firstCardWaits": (gaps: { readonly names: string }) => "Erste Karte wartet auf " + gaps.names,
    "kontra.you": "dich",
    "bid.hold": "Halten",
    "bid.pass": "Weg",
    "voice.pass": "Weg",
    "voice.kontra": "Kontra",
    "voice.re": "Re",
    "voice.supra": "Supra",
    "voice.hirsch": "Hirsch",
    "voice.value18": "achtzehn",
    "voice.value20": "zwanzig",
    "voice.value22": "zweiundzwanzig",
    "voice.value23": "dreiundzwanzig",
    "voice.value24": "vierundzwanzig",
    "voice.value27": "siebenundzwanzig",
    "voice.value30": "dreißig",
    "voice.value33": "dreiunddreißig",
    "voice.value35": "fünfunddreißig",
    "voice.value36": "sechsunddreißig",
    "voice.value40": "vierzig",
    "voice.value44": "vierundvierzig",
    "voice.value45": "fünfundvierzig",
    "voice.value46": "sechsundvierzig",
    "voice.value48": "achtundvierzig",
    "voice.value50": "fünfzig",
    "voice.value54": "vierundfünfzig",
    "voice.value55": "fünfundfünfzig",
    "voice.value59": "neunundfünfzig",
    "voice.value60": "sechzig",
    "voice.value63": "dreiundsechzig",
    "voice.value66": "sechsundsechzig",
    "voice.value70": "siebzig",
    "voice.value72": "zweiundsiebzig",
    "voice.value77": "siebenundsiebzig",
    "voice.value80": "achtzig",
    "voice.value81": "einundachtzig",
    "voice.value84": "vierundachtzig",
    "voice.value88": "achtundachtzig",
    "voice.value90": "neunzig",
    "voice.value96": "sechsundneunzig",
    "voice.value99": "neunundneunzig",
    "voice.value100": "hundert",
    "voice.value108": "hundertacht",
    "voice.value110": "hundertzehn",
    "voice.value117": "hundertsiebzehn",
    "voice.value120": "hundertzwanzig",
    "voice.value121": "hunderteinundzwanzig",
    "voice.value126": "hundertsechsundzwanzig",
    "voice.value130": "hundertdreißig",
    "voice.value132": "hundertzweiunddreißig",
    "voice.value135": "hundertfünfunddreißig",
    "voice.value140": "hundertvierzig",
    "voice.value143": "hundertdreiundvierzig",
    "voice.value144": "hundertvierundvierzig",
    "voice.value150": "hundertfünfzig",
    "voice.value153": "hundertdreiundfünfzig",
    "voice.value154": "hundertvierundfünfzig",
    "voice.value156": "hundertsechsundfünfzig",
    "voice.value160": "hundertsechzig",
    "voice.value162": "hundertzweiundsechzig",
    "voice.value165": "hundertfünfundsechzig",
    "voice.value168": "hundertachtundsechzig",
    "voice.value170": "hundertsiebzig",
    "voice.value176": "hundertsechsundsiebzig",
    "voice.value180": "hundertachtzig",
    "voice.value187": "hundertsiebenundachtzig",
    "voice.value192": "hundertzweiundneunzig",
    "voice.value198": "hundertachtundneunzig",
    "voice.value204": "zweihundertvier",
    "voice.value216": "zweihundertsechzehn",
    "voice.value240": "zweihundertvierzig",
    "voice.value264": "zweihundertvierundsechzig",
    "game.forehand": "Vorhand",
    "game.middlehand": "Mittelhand",
    "game.rearhand": "Hinterhand",
    "game.handName": (gaps: { readonly game: string }) => gaps.game + " Hand",
    "game.announcedSchneider": "Schneider angesagt",
    "game.announcedSchwarz": "Schwarz angesagt",
    "game.ouvertName": (gaps: { readonly game: string }) => gaps.game + " ouvert",
    "game.ouvertHandName": (gaps: { readonly game: string }) => gaps.game + " ouvert Hand",
    "game.karo": "Karo",
    "game.herz": "Herz",
    "game.pik": "Pik",
    "game.kreuz": "Kreuz",
    "game.grand": "Grand",
    "game.null": "Null",
    "game.ramsch": "Ramsch",
    "game.rankSeven": "Sieben",
    "game.rankEight": "Acht",
    "game.rankNine": "Neun",
    "game.rankTen": "Zehn",
    "game.rankJack": "Bube",
    "game.rankQueen": "Dame",
    "game.rankKing": "König",
    "game.rankAce": "Ass",
    "game.cardName": (gaps: { readonly rank: string; readonly suit: string }) => gaps.suit + " " + gaps.rank,
    "legal.imprint": "Impressum",
    "legal.privacy": "Datenschutz",
    "legal.terms": "Nutzungsbedingungen",
    "sound.panelName": "Ton und Bewegung",
    "sound.muted": "Ton aus",
    "sound.on": "Ton",
    "sound.tone": "Ton",
    "sound.volume": "Lautstärke",
    "sound.sets": "Klänge",
    "sound.voice": "Stimme",
    "sound.motion": "Bewegung",
    "sound.replayMotion": "Bewegung trotzdem abspielen",
    "sound.reducedMotionNote": "Dein Gerät sagt „Bewegung reduzieren“. Darum zeigt Skat jeden Zustand sofort.",
    "sound.playsOnce": "spielt einmal",
    "sound.more": "mehr",
    "sound.setLeise": "Leise",
    "sound.setStammtisch": "Stammtisch",
    "sound.setFunkeln": "Funkeln",
    "sound.lastTrick": "Letzter Stich",
    "sound.lastTrickSweep": "wegfegen",
    "sound.lastTrickStay": "liegen lassen",
    "sound.motionDezent": "dezent",
    "sound.motionVerspielt": "verspielt",
    "card.letterJack": "B",
    "card.letterQueen": "D",
    "card.letterKing": "K",
    "card.letterAce": "A",
    "agents.pill": "Agenten",
    "table.agentSits": (gaps: { readonly name: string }) => gaps.name + " setzt sich",
    "table.agentLeft": (gaps: { readonly name: string }) => gaps.name + " ist gegangen",
    "table.standUpNotice": (gaps: { readonly name: string }) => gaps.name + " ist aufgestanden",
    "table.chairLocked": "Gesperrt",
    "table.playsOn": (gaps: { readonly name: string }) => gaps.name + " spielt weiter",
    "table.playingOn": (gaps: { readonly names: string }) => gaps.names + " spielen weiter",
    "table.sitQuestion": "Mitten ins Spiel setzen?",
    "table.sitQuestionCancel": "Abbrechen",
    "table.close": "Tisch schließen",
    "table.closeQuestion": "Tisch für alle schließen?",
    "table.closeConfirm": "Schließen",
    "table.closeCancel": "Abbrechen",
    "table.takeOverNamed": (gaps: { readonly name: string }) => "Du übernimmst " + gaps.name + "s Karten.",
    "table.takeOverApostrophe": (gaps: { readonly name: string }) => "Du übernimmst " + gaps.name + "’ Karten.",
    "table.takeOverUnnamed": "Du übernimmst die Karten dieses Platzes.",
    "logout.button": "Abmelden",
    "start.rulePoints": "Laufende Augen zeigen",
    "start.rulePointsLine": "Alle sehen die Augen im Spiel",
    "start.ruleSets": "Regeln",
    "start.setOfficial": "Offiziell",
    "start.setsUnreadable": "Deine eigenen Regeln ließen sich nicht lesen.",
    "start.saveRules": "Als eigene Regeln speichern",
    "start.saveName": "Name",
    "start.savedNameWith": (gaps: { readonly rules: string; readonly set: string }) => gaps.set + ", mit " + gaps.rules,
    "start.savedNameAdjusted": (gaps: { readonly set: string }) => gaps.set + ", angepasst",
    "start.saveNameTaken": "Diesen Namen hast du schon für andere Regeln.",
    "start.saveFailed": "Die Regeln ließen sich nicht speichern.",
    "start.ruleKontra": "Kontra und Re",
    "start.ruleKontraLine": "Verdoppeln und zurückdoppeln",
    "start.ruleRamsch": "Ramsch beim Einpassen",
    "start.ruleRamschLine": "Alle passen: jeder gegen jeden",
    "start.rulePushing": "Schieberamsch",
    "start.rulePushingLine": "Den Skat weiterschieben",
    "start.ruleBock": "Bockrunden",
    "start.ruleBockLine": "Manche Spiele zählen doppelt",
    "start.askKontraSayer": "Wer darf Kontra sagen?",
    "start.pillAnyOpponent": "Jeder Gegner",
    "start.pillBiddersOnly": "Nur wer gereizt hat",
    "start.askKontraReach": "Wie weit geht es?",
    "start.pillKontraRe": "Kontra, Re",
    "start.pillKontraReStandings": "mit Ständen",
    "start.pillUpToHirsch": "bis Hirsch",
    "start.askRamschScoring": "Wie zählt der Ramsch?",
    "start.pillScoringPoints": "Augen",
    "start.pillScoringPointsByTen": "Augen durch 10",
    "start.pillScoringSkatToLoser": "Skat zum Verlierer",
    "start.askJungfrau": "Jungfrau (kein Stich)",
    "start.pillJungfrauDoublesLoser": "Verlierer doppelt",
    "start.pillJungfrauOff": "Aus",
    "start.askDurchmarsch": "Durchmarsch (alle Stiche)",
    "start.pillDurchmarschWins120": "Gewinnt 120",
    "start.pillDurchmarschWins120Flat": "120, nicht doppelt",
    "start.pillDurchmarschOff": "Aus",
    "start.askPushingRule": "Was beim Schieben gilt",
    "start.pillPushingJacksStay": "Buben bleiben",
    "start.pillPushingJacksMayGo": "Buben dürfen weg",
    "start.pillPushingNoDoubling": "Nicht doppelt",
    "start.askGrandHand": "Grand Hand statt Ramsch",
    "start.pillGrandHandOff": "Aus",
    "start.pillGrandHandAllowed": "Erlaubt",
    "start.askBockTriggers": "Bock gibt es nach",
    "start.flagSixtySixty": "60 zu 60",
    "start.flagWonGrandHand": "Grand Hand gewonnen",
    "start.flagLostAfterKontra": "Verloren nach Kontra",
    "start.flagRe": "Re",
    "start.flagPassedIn": "Alle gepasst",
    "start.flagSchneider": "Schneider",
    "start.askBockOverlap": "Neuer Auslöser im Bock",
    "start.pillOverlapAppend": "Runden dazu",
    "start.pillOverlapMultiply": "Nochmal doppelt",
    "start.pillOverlapIgnore": "Zählt nicht",
    "rules.button": "Regeln",
    "rules.title": "Regeln",
    "rules.lockBadge": "Fest für diesen Tisch",
    "rules.lockInfo": "Andere Regeln heißen neuer Tisch.",
    "rules.info": "Info",
    "rules.close": "Schließen",
    "rules.chipOfficial": "Offiziell",
    "rules.chipPoints": "Augen",
    "rules.chipKontra": "Kontra",
    "rules.chipRamsch": "Ramsch",
    "rules.namePoints": "Laufende Augen zeigen",
    "rules.nameKontra": "Kontra und Re",
    "rules.nameRamsch": "Ramsch beim Einpassen",
    "rules.nameRamschBockRounds": "Ramschrunde nach jeder Bockrunde",
    "rules.nameRamschPassedInAndBockRounds": "Ramsch beim Einpassen und Ramschrunde nach jeder Bockrunde",
    "rules.namePushing": "Schieberamsch",
    "rules.nameBock": "Bockrunden",
    "rules.pointsFromTricks": "Aus fertigen Stichen, nie in einer Null",
    "rules.kontraSayerAnyOpponent": "Jeder Gegner",
    "rules.kontraSayerBiddersOnly": "Nur wer gereizt hat",
    "rules.kontraReachKontraRe": "Nur Kontra und Re",
    "rules.kontraReachKontraReStandings": "Kontra und Re, auch 50 und 40",
    "rules.kontraReachUpToHirsch": "bis Hirsch",
    "rules.kontraDeadlineOwnCard": "bis zur eigenen Karte",
    "rules.kontraDeadlineFirstCard": "bis zur ersten Karte",
    "rules.ramschScoringPoints": "Meiste Augen minus",
    "rules.ramschScoringPointsByTen": "Augen durch zehn",
    "rules.ramschScoringSkatToLoser": "Skat zum Verlierer",
    "rules.jungfrauDoublesLoser": "Jungfrau ×2",
    "rules.jungfrauOff": "Jungfrau ohne Wirkung",
    "rules.durchmarschWins120": "Durchmarsch +120",
    "rules.durchmarschWins120Flat": "Durchmarsch +120, nie doppelt",
    "rules.durchmarschOff": "Kein Durchmarsch",
    "rules.pushingJacksStay": "Ohne Buben, je doppelt",
    "rules.pushingJacksMayGo": "Mit Buben, je doppelt",
    "rules.pushingNoDoubling": "Ohne Verdopplung",
    "rules.grandHandAllowed": "Grand Hand statt Ramsch",
    "rules.bockTriggers": (gaps: { readonly triggers: string }) => "Bei " + gaps.triggers,
    "rules.bockTriggerSixtySixty": "60 zu 60",
    "rules.bockTriggerWonGrandHand": "gewonnenem Grand Hand",
    "rules.bockTriggerLostAfterKontra": "Verlust nach Kontra",
    "rules.bockTriggerRe": "Re",
    "rules.bockTriggerPassedIn": "Einpassen",
    "rules.bockTriggerSchneider": "Schneider",
    "rules.bockTriggerSchwarz": "Schwarz",
    "rules.bockTriggerTotalEndingIn00": "Stand auf 00",
    "rules.bockOverlapAppend": "neue Runden hängen sich an",
    "rules.bockOverlapMultiply": "neue Runden multiplizieren sich",
    "rules.bockOverlapIgnore": "neue Runden zählen nicht",
};
export type Key = keyof Words;
