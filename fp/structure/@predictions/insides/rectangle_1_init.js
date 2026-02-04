function(VARS,element,context){
    
    const groups = [
        {
            id:"КАЗАХСТАН",
            items:[
                {
                    id:"Потребление",
                    value:`
                        $$("Северная зона Казахстана/Потребление")
                        + $$("Южная зона Казахстана/Потребление") + $$("Западная зона Казахстана/Потребление")
                    `,
                    factor:0.001
                },
                {
                    id:"Выработка электроэнергии",
                    items:[
                        {
                            id:"Всего",
                            value:`
                                $$("КАЗАХСТАН/Выработка электроэнергии/ТЭС") 
                                + $$("КАЗАХСТАН/Выработка электроэнергии/ГЭС")
                                + $$("КАЗАХСТАН/Выработка электроэнергии/Малые ГЭС (ВИЭ)")
                                + $$("КАЗАХСТАН/Выработка электроэнергии/ГТЭС")
                                + $$("КАЗАХСТАН/Выработка электроэнергии/ВЭС")
                                + $$("КАЗАХСТАН/Выработка электроэнергии/СЭС")
                                + $$("КАЗАХСТАН/Выработка электроэнергии/БГУ")
                            `,
                            factor:0.001
                        },
                        {
                            id:"ТЭС",
                            value:`
                                $$("Северная зона Казахстана/Выработка/ТЭС")
                                + $$("Южная зона Казахстана/Выработка/ТЭС") + $$("Западная зона Казахстана/Выработка/ТЭС")
                            `,
                            factor:0.001
                        },
                        {
                            id:"ГЭС",
                            value:`
                                $$("Северная зона Казахстана/Выработка/ГЭС")
                                + $$("Южная зона Казахстана/Выработка/ГЭС")
                            `,
                            factor:0.001
                        },
                        {
                            id:"Малые ГЭС (ВИЭ)",
                            value:`
                                $$("Северная зона Казахстана/Выработка/Малые ГЭС (ВИЭ)")
                                + $$("Южная зона Казахстана/Выработка/Малые ГЭС (ВИЭ)")
                            `,
                            factor:0.001
                        },
                        {
                            id:"ГТЭС",
                            value:`
                                $$("Северная зона Казахстана/Выработка/ГТЭС")
                                + $$("Южная зона Казахстана/Выработка/ГТЭС") + $$("Западная зона Казахстана/Выработка/ГТЭС")
                            `,
                            factor:0.001
                        },
                        {
                            id:"ВЭС",
                            value:`
                                $$("Северная зона Казахстана/Выработка/ВЭС")
                                + $$("Южная зона Казахстана/Выработка/ВЭС") + $$("Западная зона Казахстана/Выработка/ВЭС")
                            `,
                            factor:0.001
                        },
                        {
                            id:"СЭС",
                            value:`
                                $$("Северная зона Казахстана/Выработка/СЭС")
                                + $$("Южная зона Казахстана/Выработка/СЭС") + $$("Западная зона Казахстана/Выработка/СЭС")
                            `,
                            factor:0.001
                        },
                        {
                            id:"БГУ",
                            value:`
                                $$("Северная зона Казахстана/Выработка/БГУ")
                            `,
                            factor:0.001
                        }
                    ]
                }
            ]
        },{
            id:"Северная зона Казахстана",
            items:[
                {
                    id:"Потребление",
                    value:{
                        archives:[
                            "/KAZ/VOSTOK/@regions/East Kazakhstan/load/@models/P_watt/archives/day",
                            "/KAZ/VOSTOK/@regions/Abai/load/@models/P_watt/archives/day",
                            "/KAZ/CENTER/@regions/Karaganda/load/@models/P_watt/archives/day",
                            "/KAZ/CENTER/@regions/Ulytau/load/@models/P_watt/archives/day",
                            "/KAZ/KOSTANAY/@regions/Kostanay/load/@models/P_watt/archives/day",
                            "/KAZ/SEVER/@regions/Pavlodar/load/@models/P_watt/archives/day",
                            "/KAZ/AKMOLA/@regions/Akmola/load/@models/@models/P_watt/archives/day",
                            "/KAZ/AKMOLA/@regions/Kokshetau/load/@models/P_watt/archives/day",
                            "/KAZ/AKMOLA/@regions/North Kazakhstan/load/@models/P_watt/archives/day",
                            "/KAZ/AKTOBE/@regions/Aktobe/load/@models/P_watt/archives/day"
                        ],
                        aggregate:"integral"
                    },
                    factor:0.001
                },
                {
                    id:"Выработка",
                    items:[
                        {
                            id:"ТЭС",
                            value:{
                                archives:[
                                    // Восточно-Казахстанская область
                                    "/KAZ/VOSTOK/UK_TEC/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Sogr_TEC/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Rid_TEC/@models/P_watt/archives/day",

                                    // Абайская область
                                    "/KAZ/VOSTOK/Sem_TEC-1/@models/P_watt/archives/day",

                                    // Карагандинская область
                                    "/KAZ/CENTER/Kar_GRES-1/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Kar_GRES-2/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Balh_TEC/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/TEC-1/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Kar_TEC-2/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Kar_TEC-3/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Shaht_TEC/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/PVS_TEC-1/@models/P_watt/archives/day",

                                    // Улытауская область
                                    "/KAZ/CENTER/Jezkaz_TEC/@models/P_watt/archives/day",

                                    // Костанайская область
                                    "/KAZ/KOSTANAY/SSGPO_TEC/@models/P_watt/archives/day",
                                    "/KAZ/KOSTANAY/Kost_TEC/@models/P_watt/archives/day",
                                    "/KAZ/KOSTANAY/Kost_TEC-2/@models/P_watt/archives/day",
                                    "/KAZ/KOSTANAY/Arkal_TEC/@models/P_watt/archives/day",

                                    // Павлодарская область
                                    "/KAZ/SEVER/E_GRES-1/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/E_GRES-2/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/Ekib_TEC/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/Pavl_TEC-1/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/Pavl_TEC-2/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/Pavl_TEC-3/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/Aksu_GRES/@models/P_watt/archives/day",
                                    "/KAZ/SEVER/UPNK/@models/P_watt/archives/day",

                                    // Акмолинская область
                                    "/KAZ/AKMOLA/Akm_TEC-1/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Akm_TEC-2/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Step_TEC/@models/P_watt/archives/day",

                                    // Сев.Казахстанская область
                                    "/KAZ/AKMOLA/PP_TEC-2/@models/P_watt/archives/day",

                                    //Актюбинская область
                                    "/KAZ/AKTOBE/Ak_TEC/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/AZF_ES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/PTES-160/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ГЭС",
                            value:{
                                archives:[
                                    // Восточно-Казахстанская область
                                    "/KAZ/VOSTOK/B_GES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/UK_GES/@models/P_watt/archives/day",

                                    // Абайская область
                                    "/KAZ/VOSTOK/Sh_GES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"Малые ГЭС (ВИЭ)",
                            value:{
                                archives:[
                                    // Восточно-Казахстанская область
                                    "/KAZ/VOSTOK/Tish_GES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Hariuzov_GES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Ulbin_GES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Tur_GES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Zaisan/@models/P_watt/archives/day",

                                    // Карагандинская область
                                    "/KAZ/CENTER/Intumak_GES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ГТЭС",
                            value:{
                                archives:[
                                    // Улытауская область
                                    "/KAZ/CENTER/Kumkol_GTES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Akshabulak_GTES/@models/P_watt/archives/day",

                                    // Актюбинская область
                                    "/KAZ/AKTOBE/Aktobe_GTY-57/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/AZF_GPP/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/J_GTES-56/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/GTES-45/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/YuKaratobe_GPES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/Bashenkol_GPES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/ARBZ/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/Voshod_GPES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/GCK_GPES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ВЭС",
                            value:{
                                archives:[
                                    //Абайская область
                                    "/KAZ/VOSTOK/Charsk_VES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Abai-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/VOSTOK/Abai-2_VES/@models/P_watt/archives/day",

                                    //Карагандинская область
                                    "/KAZ/CENTER/VES_Giper/@models/P_watt/archives/day",

                                    // Улытауская область
                                    "/KAZ/CENTER/VES_Jezkazgan/@models/P_watt/archives/day",

                                    //Костанайская область
                                    "/KAZ/KOSTANAY/Ybyrai_VES/@models/P_watt/archives/day",
                                    "/KAZ/KOSTANAY/Arkalyk_VES/@models/P_watt/archives/day",

                                    //Акмолинская область
                                    "/KAZ/AKMOLA/Ereimen-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/AstEXPO_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/GoldenE_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/GoldenE-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Borei_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Borei-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/EnergoTrust_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Turgai/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/VostVet_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Alcor_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Sofievsk_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Arkalyk-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Arkalyk-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Jasil-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Jasil-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/KrasnyYar/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/KrasnyiYar-Etalon_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Elikty-Etalon_VES/@models/P_watt/archives/day",

                                    //Сев.Казахстанская область
                                    "/KAZ/AKMOLA/Zenchen-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Zenchen-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKMOLA/Zenchen-I_VES/@models/P_watt/archives/day",


                                    // Актюбинская область
                                    "/KAZ/AKTOBE/Badamsha-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/Badamsha-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/Khromtau_VES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"БГУ",
                            value:{
                                archives:[

                                    //Карагандинская область
                                    "/KAZ/CENTER/Kurma_BGU/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"СЭС",
                            value:{
                                archives:[

                                    // Абайская область
                                    "/KAZ/VOSTOK/JangizSolar_SES/@models/P_watt/archives/day",

                                    // Карагандинская область
                                    "/KAZ/CENTER/Saran_SES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Gulshat_SES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Agadyr_SES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Agadyr-2_SES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Balhash_SES/@models/P_watt/archives/day",

                                    // Улытауская область
                                    "/KAZ/CENTER/Kengir_SES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Barg_SES/@models/P_watt/archives/day",
                                    "/KAZ/CENTER/Zhes-Solar_SES/@models/P_watt/archives/day",

                                    // Акмолинская область
                                    "/KAZ/AKMOLA/Nura_SES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                    ]
                }
            ]
        },
        {
            id:"Южная зона Казахстана",
            items:[
                {
                    id:"Потребление",
                    value:{
                        archives:[
                            "/KAZ/ALMATY/@regions/Almaty/load/@models/P_watt/archives/day",
                            "/KAZ/ALMATY/@regions/Zhetysu/load/@models/P_watt/archives/day",
                            "/KAZ/UZHNIY/@regions/Zhambyl/load/@models/P_watt/archives/day",
                            "/KAZ/UZHNIY/@regions/KysylOrda/load/@models/P_watt/archives/day",
                            "/KAZ/UZHNIY/@regions/Turkestan/load/@models/P_watt/archives/day"
                        ],
                        aggregate:"integral"
                    },
                    factor:0.001
                },
                {
                    id:"Выработка",
                    items:[
                        {
                            id:"ТЭС",
                            value:{
                                archives:[
                                    // Алматинская область
                                    "/KAZ/ALMATY/Alm_TEC-3/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Alm_TEC-2/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Alm_TEC-1/@models/P_watt/archives/day",

                                    //Жетысуская область
                                    "/KAZ/ALMATY/Tekeli_TEC-2/@models/P_watt/archives/day",

                                    //Жамбылская область
                                    "/KAZ/UZHNIY/J_GRES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/TEC-4/@models/P_watt/archives/day",

                                    //Кызылордская область
                                    "/KAZ/UZHNIY/Kyz_TEC-6/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/SKZU_SES/@models/P_watt/archives/day",

                                    //Туркестанская область
                                    "/KAZ/UZHNIY/SH_TEC-3/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/TEC-5/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/PKOP/@models/P_watt/archives/day"
                                    
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ГЭС",
                            value:{
                                archives:[
                                    // Алматинская область
                                    "/KAZ/ALMATY/Moinak_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kapch_GES/@models/P_watt/archives/day",

                                    //Туркестанская область
                                    "/KAZ/UZHNIY/Shar_GES/@models/P_watt/archives/day"

                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"Малые ГЭС (ВИЭ)",
                            value:{
                                archives:[
                                    // Алматинская область
                                    "/KAZ/ALMATY/Kaskad_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Talgar_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Issyk-1_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Issyk-2_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Issyk-3_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Med-2_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Chokin_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Def_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Karash_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/ECEn_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Tolkyn_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kakpak_GES/@models/P_watt/archives/day",

                                    //Жетысуская область
                                    "/KAZ/ALMATY/Anton_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Uspen_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Sarkand_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Intalin_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Aksu-1_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Baskan-1_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Baskan-2_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Lepsy_GES-2/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kora_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kora-2_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Korgas_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Karatal-1_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Karatal-2_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Karatal-3_GES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Karatal_GES-4/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Chija_GES-2/@models/P_watt/archives/day",

                                    //Жамбылская область
                                    "/KAZ/UZHNIY/Merken-1_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Merken-3_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Zhambyl_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Tasotkel_GES-1/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Tasotkel_GES-2/@models/P_watt/archives/day",
                                    
                                    //Туркестанская область
                                    "/KAZ/UZHNIY/Mankent_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Koshkar-Ata_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Ryszhan_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Darkhan_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Dostyk_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Kenes_GES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Intymak_GES/@models/P_watt/archives/day"

                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ГТЭС",
                            value:{
                                archives:[
                                    //Жетысуская область
                                    "/KAZ/ALMATY/Tekeli_PGU/@models/P_watt/archives/day",

                                    //Кызылордская область
                                    "/KAZ/UZHNIY/KOG_TEC/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Kyz_GTU/@models/P_watt/archives/day",

                                    //Туркестанская область
                                    "/KAZ/UZHNIY/PKOP_GTU/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Turkestan_PGU/@models/P_watt/archives/day"

                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                        
                            id:"ВЭС",
                            value:{
                                archives:[
                                    //Алматинская область
                                    "/KAZ/ALMATY/Kapch_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Nurly-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Nurly-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/VesShel1/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Shelek-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Shelek-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Sarybulak-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Sarybulak-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kerbulak-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kerbulak-2_VES/@models/P_watt/archives/day",

                                    //Жетысуская область
                                    "/KAZ/ALMATY/EcoWattAKA_VES/@models/P_watt/archives/day",

                                    //Жамбылская область
                                    "/KAZ/UZHNIY/IzenSu_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Kordai-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Kordai-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Janatas_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Shangeldy-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Shangeldy-2_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Novoteks_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Shokpar_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Koktal-1_VES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Koktal-2_VES/@models/P_watt/archives/day"

                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                        
                            id:"СЭС",
                            value:{
                                archives:[
                                    //Алматинская область
                                    "/KAZ/ALMATY/Samruk-1_SES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kapch_SES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Samruk-3_SES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Shu_SES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Kaskelen_SES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/Sarybulak_SES/@models/P_watt/archives/day",
                                    "/KAZ/ALMATY/KUNKUAT_SES/@models/P_watt/archives/day",

                                    //Жетысуская область
                                    "/KAZ/ALMATY/AEP_SES/@models/P_watt/archives/day",

                                    //Жамбылская область
                                    "/KAZ/UZHNIY/Burnoe_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Burnoe-2_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Aisha_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Aralsk_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Otar_SES/@models/P_watt/archives/day",

                                    //Кызылордская область
                                    "/KAZ/UZHNIY/SKZU_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Baiken_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Baikonyr_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Janakorgan_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Jalagash_SES/@models/P_watt/archives/day",

                                    //Туркестанская область
                                    "/KAZ/UZHNIY/Ochistnoe_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Akbai_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Zhylga_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Zadar-1_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Zadar-2_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Zhatysay_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/YuK_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Shymkent_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Kentau_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/ShokKush_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Kushata_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Makpal_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Otrar_SES/@models/P_watt/archives/day",
                                    "/KAZ/UZHNIY/Shaulder_SES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        }
                    ]
                }
            ]
        },
        {
            id:"Западная зона Казахстана",
            items:[
                {
                    id:"Потребление",
                    value:{
                        archives:[
                            "/KAZ/ZAPAD/@regions/Atyrau/load/@models/P_watt/archives/day",
                            "/KAZ/ZAPAD/@regions/Mangystau/load/@models/P_watt/archives/day",
                            "/KAZ/ZAPAD/@regions/West Kazakhstan/load/@models/P_watt/archives/day"
                        ],
                        aggregate:"integral"
                    },
                    factor:0.001
                },
                {
                    id:"Выработка",
                    items:[
                        {
                            id:"ТЭС",
                            value:{
                                archives:[
                                    // Атырауская область
                                    "/KAZ/ZAPAD/Atyr_TEC/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/ANPZ_TEC/@models/P_watt/archives/day",

                                    //Мангыстауская область
                                    "/KAZ/ZAPAD/MAEK/@models/P_watt/archives/day",

                                    //Зап. Казахстанская область
                                    "/KAZ/ZAPAD/Ural_TEC/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ГТЭС",
                            value:{
                                archives:[
                                    // Атырауская область
                                    "/KAZ/ZAPAD/GTSTShO/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/ORUTSho/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/ZVP/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/TGTES-4/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/Kashagan/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/KUS_GTES/@models/P_watt/archives/day",

                                    //Мангыстауская область
                                    "/KAZ/ZAPAD/Kalamkas_GTES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/Janaozen_GPES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/KazAzot_GPES/@models/P_watt/archives/day",

                                    //Зап. Казахстанская область
                                    "/KAZ/ZAPAD/Ural_TEC_PGU/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/KPK_GTES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/Ural_GTES/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/GTES-200/@models/P_watt/archives/day",
                                    "/KAZ/AKTOBE/GTES-26/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"СЭС",
                            value:{
                                archives:[
                                    //Мангыстауская область
                                    "/KAZ/ZAPAD/Batyr_SES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        },
                        {
                            id:"ВЭС",
                            value:{
                                archives:[
                                    // Атырауская область
                                    "/KAZ/ZAPAD/Taiman_VES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/Dossor_VES/@models/P_watt/archives/day",

                                    //Мангыстауская область
                                    "/KAZ/ZAPAD/Servis_VES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/Jangiz_VES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/Akshukur_VES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/SarkylmasKuat_VES/@models/P_watt/archives/day",
                                    "/KAZ/ZAPAD/FortShevch_VES/@models/P_watt/archives/day"
                                ],
                                aggregate:"integral"
                            },
                            factor:0.001
                        }
                    ]
                }
            ]
        }
    ];
    
    fp.rt.load_library("/root/FP/prototypes/global_library/content/predict_report").then(report => {
        report(groups, element.get_element(), context.get_connection(), fp_dev, { dayHours: 30, monthDays: 45, yearMonths: 18 } );
    });
}