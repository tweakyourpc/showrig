// Supplementary words layered on top of dictionary.js.
//
// dictionary.js is the word list that came from the original Anagram Artist
// for Windows and is left exactly as it was found, so its provenance stays
// intact. Words that the original omits are added here instead, each with a
// reason, so every departure from the original data is visible and reversible.
//
// Words are merged at load time (see hydrateDictionary in main.js) and picked
// up by tools/build-dictionary.mjs, so additions get the same commonness,
// part-of-speech, syllable, stress, rhyme and synonym data as everything else.
//
// Duplicates of words already in dictionary.js are ignored, so it is safe to
// list something without checking first.

window.dictionaryAdditions = [
    // -----------------------------------------------------------------
    // Omissions
    // -----------------------------------------------------------------

    // The original has America, Americas, Americana, Americans,
    // Americanism and Americanise/Americanize, but not the singular
    // "American" - a gap that also swallowed the exact anagram of AMERICAN.
    'American',

    // -----------------------------------------------------------------
    // American spellings
    //
    // The dictionary already carries both members of 863 British/American
    // spelling pairs, marked with the internal capital described in
    // DATA_SOURCES.md (coloR/coloUr, coSy/cozY). These are the pairs where
    // only the British form made it in, so this completes a pattern the
    // dictionary already follows rather than introducing a new one.
    //
    // Taken from a curated British-to-American spelling map (see
    // DATA_SOURCES.md), restricted to cases where the British form is
    // already present and the American one is not. Forms longer than 13
    // letters are excluded: the dictionary caps at 13 and the suggestion
    // columns stop there, so they would never be shown.
    // -----------------------------------------------------------------

    // Independently attested in the Google Books ngram frequency data
    // and/or CMUdict.
    'accouterments',    // accoutrements
    'calisthenics',     // callisthenics
    'chiseling',        // chiselling
    'cudgeled',         // cudgelled
    'cudgeling',        // cudgelling
    'driveled',         // drivelled
    'driveling',        // drivelling
    'dueled',           // duelled
    'enthrall',         // enthral
    'epilog',           // epilogue
    'esthete',          // aesthete
    'esthetic',         // aesthetic
    'esthetically',     // aesthetically
    'gasses',           // gases
    'grayish',          // greyish
    'grueling',         // gruelling
    'gynecologist',     // gynaecologist
    'gynecology',       // gynaecology
    'harmonized',       // harmonised
    'harmonizes',       // harmonises
    'harmonizing',      // harmonising
    'homeopathy',       // homoeopathy
    'impaneled',        // impanelled
    'impaneling',       // impanelling
    'imperiling',       // imperilling
    'instill',          // instil
    'instills',         // instils
    'jailbird',         // gaolbird
    'marshaling',       // marshalling
    'misbehavior',      // misbehaviour
    'modeled',          // modelled
    'modeler',          // modeller
    'modeling',         // modelling
    'pedaled',          // pedalled
    'pedaling',         // pedalling
    'penciled',         // pencilled
    'penciling',        // pencilling
    'pharmacopeia',     // pharmacopoeia
    'plowshares',       // ploughshares
    'prolog',           // prologue
    'pummeled',         // pummelling
    'raveling',         // ravelling
    'revelers',         // revellers
    'rivaled',          // rivalled
    'rivaling',         // rivalling
    'sniveled',         // snivelled
    'sniveling',        // snivelling
    'toweling',         // towelling
    'traveled',         // travelled
    'traveling',        // travelling
    'travelog',         // travelogue
    'tunneling',        // tunnelling
    'wooly',            // woolly

    // From the curated map but without independent attestation in the
    // ngram data or CMUdict - almost all are regular inflections of forms
    // listed above. Delete this block if you would rather not carry them.
    'cancelation',      // cancellation
    'cancelations',     // cancellations
    'colorants',        // colourants
    'decentralizes',    // decentralises
    'disemboweled',     // disembowelled
    'epilogs',          // epilogues
    'esophaguses',      // oesophaguses
    'esthetes',         // aesthetes
    'fileted',          // filleted
    'fileting',         // filleting
    'jailbirds',        // gaolbirds
    'modelers',         // modellers
    'monolog',          // monologue
    'monologs',         // monologues
    'prologs',          // prologues
    'toweled',          // towelled
    'travelogs',        // travelogues
];
