# metadata.py
# EmuCoach / TrinityCore 4.3.4-style quest_template schema (key = entry)
# Tabs are grouped for sanity: Core, Text, Objectives, Requirements, Rewards, Reputation, Currency, Scripts/Sounds, Misc.

from __future__ import annotations
from typing import List, Tuple

Field = Tuple[str, str, str]          # (column, label, ftype)
Tab = Tuple[str, List[Field]]         # (tab_name, fields)


QUEST_TABS: List[Tab] = [
    (
        "Core",
        [
            ("entry", "Quest ID", "int"),

            ("Method", "Method", "int"),
            ("ZoneOrSort", "Zone/Sort", "int"),
            ("SkillOrClassMask", "Skill/Class Mask", "int"),

            ("MinLevel", "Min Level", "int"),
            ("MaxLevel", "Max Level", "int"),
            ("QuestLevel", "Quest Level", "int"),
            ("Type", "Type", "int"),

            ("SuggestedPlayers", "Suggested Players", "int"),
            ("LimitTime", "Time Limit (sec)", "int"),

            ("QuestFlags", "Quest Flags", "int"),
            ("SpecialFlags", "Special Flags", "int"),

            ("RequiredRaces", "Required Races (mask)", "int"),
            ("RequiredSkillValue", "Required Skill Value", "int"),

            ("CharTitleId", "Char Title ID", "int"),
            ("PlayersSlain", "Players Slain", "int"),
            ("BonusTalents", "Bonus Talents", "int"),
            ("RewardArenaPoints", "Reward Arena Points", "int"),
        ],
    ),

    (
        "Chain",
        [
            ("PrevQuestId", "Prev Quest ID", "int"),
            ("NextQuestId", "Next Quest ID", "int"),
            ("ExclusiveGroup", "Exclusive Group", "int"),
            ("NextQuestInChain", "Next Quest In Chain", "int"),
        ],
    ),

    (
        "Reputation Requirements",
        [
            ("RepObjectiveFaction", "Rep Objective Faction 1", "int"),
            ("RepObjectiveValue", "Rep Objective Value 1", "int"),
            ("RepObjectiveFaction2", "Rep Objective Faction 2", "int"),
            ("RepObjectiveValue2", "Rep Objective Value 2", "int"),

            ("RequiredMinRepFaction", "Required Min Rep Faction", "int"),
            ("RequiredMinRepValue", "Required Min Rep Value", "int"),
            ("RequiredMaxRepFaction", "Required Max Rep Faction", "int"),
            ("RequiredMaxRepValue", "Required Max Rep Value", "int"),
        ],
    ),

    (
        "Source",
        [
            ("RewXPId", "Reward XP ID", "int"),

            ("SrcItemId", "Source Item ID", "int"),
            ("SrcItemCount", "Source Item Count", "int"),
            ("SrcSpell", "Source Spell", "int"),
        ],
    ),

    (
        "Text",
        [
            ("Title", "Title", "text"),
            ("Details", "Details", "text"),
            ("Objectives", "Objectives", "text"),

            ("OfferRewardText", "Offer Reward Text", "text"),
            ("RequestItemsText", "Request Items Text", "text"),
            ("EndText", "End Text", "text"),
            ("CompletedText", "Completed Text", "text"),
        ],
    ),

    (
        "Objective Text",
        [
            ("ObjectiveText1", "Objective Text 1", "text"),
            ("ObjectiveText2", "Objective Text 2", "text"),
            ("ObjectiveText3", "Objective Text 3", "text"),
            ("ObjectiveText4", "Objective Text 4", "text"),
        ],
    ),

    (
        "Requirements - Items",
        [
            ("ReqItemId1", "Req Item ID 1", "int"),
            ("ReqItemCount1", "Req Item Count 1", "int"),
            ("ReqItemId2", "Req Item ID 2", "int"),
            ("ReqItemCount2", "Req Item Count 2", "int"),
            ("ReqItemId3", "Req Item ID 3", "int"),
            ("ReqItemCount3", "Req Item Count 3", "int"),
            ("ReqItemId4", "Req Item ID 4", "int"),
            ("ReqItemCount4", "Req Item Count 4", "int"),
            ("ReqItemId5", "Req Item ID 5", "int"),
            ("ReqItemCount5", "Req Item Count 5", "int"),
            ("ReqItemId6", "Req Item ID 6", "int"),
            ("ReqItemCount6", "Req Item Count 6", "int"),
        ],
    ),

    (
        "Requirements - Sources",
        [
            ("ReqSourceId1", "Req Source ID 1", "int"),
            ("ReqSourceCount1", "Req Source Count 1", "int"),
            ("ReqSourceId2", "Req Source ID 2", "int"),
            ("ReqSourceCount2", "Req Source Count 2", "int"),
            ("ReqSourceId3", "Req Source ID 3", "int"),
            ("ReqSourceCount3", "Req Source Count 3", "int"),
            ("ReqSourceId4", "Req Source ID 4", "int"),
            ("ReqSourceCount4", "Req Source Count 4", "int"),
        ],
    ),

    (
        "Requirements - NPC/GO",
        [
            ("ReqCreatureOrGOId1", "Req NPC/GO ID 1", "int"),
            ("ReqCreatureOrGOCount1", "Req NPC/GO Count 1", "int"),
            ("ReqCreatureOrGOId2", "Req NPC/GO ID 2", "int"),
            ("ReqCreatureOrGOCount2", "Req NPC/GO Count 2", "int"),
            ("ReqCreatureOrGOId3", "Req NPC/GO ID 3", "int"),
            ("ReqCreatureOrGOCount3", "Req NPC/GO Count 3", "int"),
            ("ReqCreatureOrGOId4", "Req NPC/GO ID 4", "int"),
            ("ReqCreatureOrGOCount4", "Req NPC/GO Count 4", "int"),
        ],
    ),

    (
        "Requirements - Spell Cast",
        [
            ("ReqSpellCast1", "Req Spell Cast 1", "int"),
            ("ReqSpellCast2", "Req Spell Cast 2", "int"),
            ("ReqSpellCast3", "Req Spell Cast 3", "int"),
            ("ReqSpellCast4", "Req Spell Cast 4", "int"),
        ],
    ),

    (
        "Rewards - Choice Items",
        [
            ("RewChoiceItemId1", "Choice Item ID 1", "int"),
            ("RewChoiceItemCount1", "Choice Item Count 1", "int"),
            ("RewChoiceItemId2", "Choice Item ID 2", "int"),
            ("RewChoiceItemCount2", "Choice Item Count 2", "int"),
            ("RewChoiceItemId3", "Choice Item ID 3", "int"),
            ("RewChoiceItemCount3", "Choice Item Count 3", "int"),
            ("RewChoiceItemId4", "Choice Item ID 4", "int"),
            ("RewChoiceItemCount4", "Choice Item Count 4", "int"),
            ("RewChoiceItemId5", "Choice Item ID 5", "int"),
            ("RewChoiceItemCount5", "Choice Item Count 5", "int"),
            ("RewChoiceItemId6", "Choice Item ID 6", "int"),
            ("RewChoiceItemCount6", "Choice Item Count 6", "int"),
        ],
    ),

    (
        "Rewards - Guaranteed Items",
        [
            ("RewItemId1", "Reward Item ID 1", "int"),
            ("RewItemCount1", "Reward Item Count 1", "int"),
            ("RewItemId2", "Reward Item ID 2", "int"),
            ("RewItemCount2", "Reward Item Count 2", "int"),
            ("RewItemId3", "Reward Item ID 3", "int"),
            ("RewItemCount3", "Reward Item Count 3", "int"),
            ("RewItemId4", "Reward Item ID 4", "int"),
            ("RewItemCount4", "Reward Item Count 4", "int"),
        ],
    ),

    (
        "Rewards - Money/Spells/Mail",
        [
            ("RewOrReqMoney", "Reward/Req Money", "int"),
            ("RewMoneyMaxLevel", "Money at Max Level", "int"),

            ("RewSpell", "Reward Spell", "int"),
            ("RewSpellCast", "Reward Spell Cast", "int"),

            ("RewMailTemplateId", "Mail Template ID", "int"),
            ("RewMailDelaySecs", "Mail Delay (sec)", "int"),
        ],
    ),

    (
        "Rewards - Skills/Honor",
        [
            ("RewHonorAddition", "Honor Addition", "int"),
            ("RewHonorMultiplier", "Honor Multiplier", "float"),

            ("RewSkillLineId", "Reward Skill Line ID", "int"),
            ("RewSkillPoints", "Reward Skill Points", "int"),
        ],
    ),

    (
        "Rewards - Reputation",
        [
            ("RewRepFaction1", "Rep Faction 1", "int"),
            ("RewRepValueId1", "Rep Value ID 1", "int"),
            ("RewRepValue1", "Rep Value 1", "int"),

            ("RewRepFaction2", "Rep Faction 2", "int"),
            ("RewRepValueId2", "Rep Value ID 2", "int"),
            ("RewRepValue2", "Rep Value 2", "int"),

            ("RewRepFaction3", "Rep Faction 3", "int"),
            ("RewRepValueId3", "Rep Value ID 3", "int"),
            ("RewRepValue3", "Rep Value 3", "int"),

            ("RewRepFaction4", "Rep Faction 4", "int"),
            ("RewRepValueId4", "Rep Value ID 4", "int"),
            ("RewRepValue4", "Rep Value 4", "int"),

            ("RewRepFaction5", "Rep Faction 5", "int"),
            ("RewRepValueId5", "Rep Value ID 5", "int"),
            ("RewRepValue5", "Rep Value 5", "int"),

            ("RewRepMask", "Rep Mask", "int"),
        ],
    ),

    (
        "Rewards - Currency",
        [
            ("RewCurrencyId1", "Reward Currency ID 1", "int"),
            ("RewCurrencyCount1", "Reward Currency Count 1", "int"),
            ("RewCurrencyId2", "Reward Currency ID 2", "int"),
            ("RewCurrencyCount2", "Reward Currency Count 2", "int"),
            ("RewCurrencyId3", "Reward Currency ID 3", "int"),
            ("RewCurrencyCount3", "Reward Currency Count 3", "int"),
            ("RewCurrencyId4", "Reward Currency ID 4", "int"),
            ("RewCurrencyCount4", "Reward Currency Count 4", "int"),
        ],
    ),

    (
        "Requirements - Currency",
        [
            ("ReqCurrencyId1", "Req Currency ID 1", "int"),
            ("ReqCurrencyCount1", "Req Currency Count 1", "int"),
            ("ReqCurrencyId2", "Req Currency ID 2", "int"),
            ("ReqCurrencyCount2", "Req Currency Count 2", "int"),
            ("ReqCurrencyId3", "Req Currency ID 3", "int"),
            ("ReqCurrencyCount3", "Req Currency Count 3", "int"),
            ("ReqCurrencyId4", "Req Currency ID 4", "int"),
            ("ReqCurrencyCount4", "Req Currency Count 4", "int"),
        ],
    ),

    (
        "Portraits",
        [
            ("QuestGiverPortrait", "Quest Giver Portrait", "int"),
            ("QuestTurnInPortrait", "Quest Turn-In Portrait", "int"),

            ("QuestGiverPortraitText", "Giver Portrait Text", "text"),
            ("QuestGiverPortraitUnk", "Giver Portrait Unk", "text"),
            ("QuestTurnInPortraitText", "Turn-In Portrait Text", "text"),
            ("QuestTurnInPortraitUnk", "Turn-In Portrait Unk", "text"),

            ("QuestTargetMark", "Quest Target Mark", "int"),
            ("QuestStartType", "Quest Start Type", "int"),
        ],
    ),

    (
        "Emotes",
        [
            ("DetailsEmote1", "Details Emote 1", "int"),
            ("DetailsEmoteDelay1", "Details Emote Delay 1", "int"),
            ("DetailsEmote2", "Details Emote 2", "int"),
            ("DetailsEmoteDelay2", "Details Emote Delay 2", "int"),
            ("DetailsEmote3", "Details Emote 3", "int"),
            ("DetailsEmoteDelay3", "Details Emote Delay 3", "int"),
            ("DetailsEmote4", "Details Emote 4", "int"),
            ("DetailsEmoteDelay4", "Details Emote Delay 4", "int"),

            ("IncompleteEmote", "Incomplete Emote", "int"),
            ("CompleteEmote", "Complete Emote", "int"),

            ("OfferRewardEmote1", "Offer Reward Emote 1", "int"),
            ("OfferRewardEmoteDelay1", "Offer Reward Delay 1", "int"),
            ("OfferRewardEmote2", "Offer Reward Emote 2", "int"),
            ("OfferRewardEmoteDelay2", "Offer Reward Delay 2", "int"),
            ("OfferRewardEmote3", "Offer Reward Emote 3", "int"),
            ("OfferRewardEmoteDelay3", "Offer Reward Delay 3", "int"),
            ("OfferRewardEmote4", "Offer Reward Emote 4", "int"),
            ("OfferRewardEmoteDelay4", "Offer Reward Delay 4", "int"),
        ],
    ),

    (
        "Point",
        [
            ("PointMapId", "Point Map ID", "int"),
            ("PointX", "Point X", "float"),
            ("PointY", "Point Y", "float"),
            ("PointOpt", "Point Opt", "int"),
        ],
    ),

    (
        "Sounds/Scripts",
        [
            ("SoundAccept", "Sound Accept", "int"),
            ("SoundTurnIn", "Sound Turn-In", "int"),
            ("RequiredSpell", "Required Spell", "int"),
            ("StartScript", "Start Script", "int"),
            ("CompleteScript", "Complete Script", "int"),
        ],
    ),

    (
        "Misc",
        [
            ("RewRepMask", "Reward Rep Mask", "int"),
            ("unk0", "unk0", "int"),
            ("WDBVerified", "WDB Verified", "int"),
        ],
    ),
]
