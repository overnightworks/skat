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
    readonly "lobby.myTables": string;
    readonly "lobby.openTable": (gaps: { readonly title: string }) => string;
    readonly "lobby.title": (gaps: { readonly owner: string }) => string;
    readonly "lobby.titleNameless": string;
    readonly "lobby.progress": (gaps: { readonly count: number; readonly game: string }) => string;
    readonly "lobby.length": (count: number) => string;
    readonly "lobby.sideYou": string;
    readonly "lobby.seatFree": string;
    readonly "lobby.seatAway": string;
    readonly "lobby.minutesLeft": (count: number, gaps: { readonly minutes: string }) => string;
    readonly "lobby.ownSeatFreeIn": (count: number, gaps: { readonly minutes: string }) => string;
    readonly "lobby.otherSeatFreeIn": (count: number, gaps: { readonly minutes: string; readonly owner: string }) => string;
    readonly "lobby.chipYourTurn": string;
    readonly "lobby.chipResultWaits": string;
    readonly "lobby.chipSeriesOver": string;
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
    readonly "table.waitingFor": string;
    readonly "table.wantsToGiveUp": (gaps: { readonly name: string }) => string;
    readonly "table.givesUp": (gaps: { readonly name: string }) => string;
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
    readonly "table.gives": string;
    readonly "table.waitsForYou": string;
    readonly "table.bidValue": string;
    readonly "table.plays": string;
    readonly "table.chooses": string;
    readonly "table.discards": string;
    readonly "table.ramsch": string;
    readonly "table.pushCount": (gaps: { readonly count: number }) => string;
    readonly "table.pushFactor": (gaps: { readonly factor: string }) => string;
    readonly "table.push": string;
    readonly "table.thinks": string;
    readonly "table.dealer": string;
    readonly "table.cardCount": string;
    readonly "table.open": string;
    readonly "table.openForAll": string;
    readonly "table.sideYou": string;
    readonly "table.weiter": string;
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
    readonly "result.and": string;
    readonly "result.declarerWins": (gaps: { readonly name: string }) => string;
    readonly "result.declarerLoses": (gaps: { readonly name: string }) => string;
    readonly "result.opponentGameLine": (gaps: { readonly declarer: string; readonly game: string }) => string;
    readonly "result.missedSchneider": string;
    readonly "result.missedSchwarz": string;
    readonly "result.raise": (gaps: { readonly bid: string; readonly settled: string; readonly value: string }) => string;
    readonly "bock.factor": (gaps: { readonly factor: string }) => string;
    readonly "bock.times": (gaps: { readonly factor: string }) => string;
    readonly "rules.chipBock": string;
    readonly "rules.bockLeft": (gaps: { readonly count: number }) => string;
    readonly "result.sidePoints": (gaps: { readonly points: string; readonly side: string }) => readonly (string | { readonly marker: "side" | "tally"; readonly text: string })[];
    readonly "result.eyes": (gaps: { readonly points: string }) => string;
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
    readonly "declare.commandFailed": string;
    readonly "declare.takeSkat": string;
    readonly "push.takeSkat": string;
    readonly "declare.putBack": string;
    readonly "declare.announceGame": string;
    readonly "declare.hand": string;
    readonly "declare.levelSchneider": string;
    readonly "declare.levelSchwarz": string;
    readonly "declare.levelOuvert": string;
    readonly "play.commandFailed": string;
    readonly "play.sideUs": string;
    readonly "play.sideThem": string;
    readonly "play.trick": string;
    readonly "play.sideYou": string;
    readonly "kontra.kontra": string;
    readonly "kontra.re": string;
    readonly "kontra.supra": string;
    readonly "kontra.hirsch": string;
    readonly "kontra.stamp": (gaps: { readonly word: string }) => string;
    readonly "kontra.saidBy": (gaps: { readonly name: string; readonly word: string }) => string;
    readonly "kontra.commandFailed": string;
    readonly "bid.hold": string;
    readonly "bid.pass": string;
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
    readonly "table.sitQuestion": string;
    readonly "table.sitQuestionCancel": string;
    readonly "table.takeOverNamed": (gaps: { readonly name: string }) => string;
    readonly "table.takeOverApostrophe": (gaps: { readonly name: string }) => string;
    readonly "table.takeOverUnnamed": string;
    readonly "logout.button": string;
    readonly "start.rulePoints": string;
    readonly "start.rulePointsLine": string;
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
    "lobby.myTables": "Meine Tische",
    "lobby.openTable": (gaps: { readonly title: string }) => gaps.title + " öffnen",
    "lobby.title": (gaps: { readonly owner: string }) => gaps.owner + " Tisch",
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
    "lobby.otherSeatFreeIn": (count: number, gaps: { readonly minutes: string; readonly owner: string }) => ({
        zero: gaps.owner + " Platz wird in " + gaps.minutes + " Minuten frei",
        one: gaps.owner + " Platz wird in " + gaps.minutes + " Minute frei",
        two: gaps.owner + " Platz wird in " + gaps.minutes + " Minuten frei",
        few: gaps.owner + " Platz wird in " + gaps.minutes + " Minuten frei",
        many: gaps.owner + " Platz wird in " + gaps.minutes + " Minuten frei",
        other: gaps.owner + " Platz wird in " + gaps.minutes + " Minuten frei",
    })[pluralRules.select(count)],
    "lobby.chipYourTurn": "Du bist dran",
    "lobby.chipResultWaits": "Ergebnis wartet",
    "lobby.chipSeriesOver": "Serie vorbei",
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
    "table.waitingFor": "Warte auf",
    "table.wantsToGiveUp": (gaps: { readonly name: string }) => gaps.name + " will aufgeben",
    "table.givesUp": (gaps: { readonly name: string }) => gaps.name + " gibt auf",
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
    "table.gives": "gibt",
    "table.waitsForYou": "wartet auf dich",
    "table.bidValue": "Reizwert",
    "table.plays": "spielt",
    "table.chooses": "wählt",
    "table.discards": "drückt",
    "table.ramsch": "Ramsch",
    "table.pushCount": (gaps: { readonly count: number }) => numberFormat.format(gaps.count) + "× geschoben",
    "table.pushFactor": (gaps: { readonly factor: string }) => "×" + gaps.factor,
    "table.push": "Schieben",
    "table.thinks": "denkt",
    "table.dealer": "Geber",
    "table.cardCount": "Karten",
    "table.open": "Offen",
    "table.openForAll": "Offen für alle",
    "table.sideYou": "Du",
    "table.weiter": "Weiter",
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
    "result.and": "und",
    "result.declarerWins": (gaps: { readonly name: string }) => gaps.name + " gewinnt",
    "result.declarerLoses": (gaps: { readonly name: string }) => gaps.name + " verliert",
    "result.opponentGameLine": (gaps: { readonly declarer: string; readonly game: string }) => gaps.declarer + ", " + gaps.game,
    "result.missedSchneider": "Schneider angesagt, nicht erreicht",
    "result.missedSchwarz": "Schwarz angesagt, nicht erreicht",
    "result.raise": (gaps: { readonly bid: string; readonly settled: string; readonly value: string }) => "Wert " + gaps.value + " < Reizwert " + gaps.bid + " → " + gaps.settled,
    "bock.factor": (gaps: { readonly factor: string }) => "Bock ×" + gaps.factor,
    "bock.times": (gaps: { readonly factor: string }) => "×" + gaps.factor,
    "rules.chipBock": "Bock",
    "rules.bockLeft": (gaps: { readonly count: number }) => "noch " + numberFormat.format(gaps.count),
    "result.sidePoints": (gaps: { readonly points: string; readonly side: string }): readonly (string | { readonly marker: "side" | "tally"; readonly text: string })[] => [{ marker: "side", text: gaps.side }, " ", { marker: "tally", text: gaps.points }],
    "result.eyes": (gaps: { readonly points: string }) => gaps.points + " Augen",
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
    "declare.commandFailed": "Das hat nicht geklappt",
    "declare.takeSkat": "Aufnehmen",
    "push.takeSkat": "Skat nehmen",
    "declare.putBack": "Drücken",
    "declare.announceGame": "Ansagen",
    "declare.hand": "Hand",
    "declare.levelSchneider": "Schneider",
    "declare.levelSchwarz": "Schwarz",
    "declare.levelOuvert": "Ouvert",
    "play.commandFailed": "Das hat nicht geklappt",
    "play.sideUs": "Wir",
    "play.sideThem": "Gegner",
    "play.trick": "Stich",
    "play.sideYou": "Du",
    "kontra.kontra": "Kontra",
    "kontra.re": "Re",
    "kontra.supra": "Supra",
    "kontra.hirsch": "Hirsch",
    "kontra.stamp": (gaps: { readonly word: string }) => gaps.word + "!",
    "kontra.saidBy": (gaps: { readonly name: string; readonly word: string }) => gaps.name + " sagt " + gaps.word,
    "kontra.commandFailed": "Das hat nicht geklappt",
    "bid.hold": "Halten",
    "bid.pass": "Weg",
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
    "table.sitQuestion": "Mitten ins Spiel setzen?",
    "table.sitQuestionCancel": "Abbrechen",
    "table.takeOverNamed": (gaps: { readonly name: string }) => "Du übernimmst " + gaps.name + "s Karten.",
    "table.takeOverApostrophe": (gaps: { readonly name: string }) => "Du übernimmst " + gaps.name + "’ Karten.",
    "table.takeOverUnnamed": "Du übernimmst die Karten dieses Platzes.",
    "logout.button": "Abmelden",
    "start.rulePoints": "Laufende Augen zeigen",
    "start.rulePointsLine": "Alle sehen die Augen im Spiel",
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
