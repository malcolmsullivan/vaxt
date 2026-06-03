# The horticultural gene sequencing field guide

*VÄXT open-source field guide · CC BY 4.0*

---

**Modern plant breeding fuses genomics with classical horticultural practice, and the open-source toolchain to do this has never been more accessible.** A breeder working with cold-hardy Nordic crops can now move from raw sequencing reads to marker-assisted selection decisions using entirely free software, modest lab equipment, and cloud-scale computation when needed. This guide walks through every layer of that stack: the bioinformatics tools that process sequence data, the genes and markers that govern cold tolerance, the Nordic breeding programs that have put these methods into practice, the statistical frameworks that connect genotype to phenotype, and the physical infrastructure required to run breeding trials from a backyard greenhouse to a commercial operation.

---

## 1. Open-source genomics tools and how to use them

The standard plant genomics pipeline follows a clear path: raw sequencing reads (FASTQ) → quality control → alignment to a reference genome → variant calling → filtering → annotation → association analysis. Every step is handled by well-maintained, free software installable through the **Bioconda** package channel (`conda install -c bioconda <tool>`).

### Alignment and variant calling core

**BWA** (Burrows-Wheeler Aligner) maps short Illumina reads to a reference genome. BWA-MEM is the primary algorithm for reads longer than 70 bp. After indexing the reference (`bwa index reference.fasta`), paired-end reads are aligned and piped directly to SAMtools for sorting:

```bash
bwa mem -t 8 -R '@RG\tID:sample1\tSM:sample1\tPL:ILLUMINA\tLB:lib1' \
  reference.fasta reads_R1.fastq.gz reads_R2.fastq.gz | \
  samtools sort -o aligned.bam
```

**SAMtools** manipulates the resulting BAM alignment files — sorting, indexing, filtering, and generating alignment statistics. Its companion **bcftools** handles variant calling from pileups and all downstream VCF manipulation, including filtering, merging, and consensus generation. A minimal variant calling pipeline in bcftools runs in two piped commands:

```bash
bcftools mpileup -Ou -f reference.fasta sorted.bam | \
  bcftools call -mv -Oz -o variants.vcf.gz
bcftools filter -e 'QUAL<30 || DP<5 || MQ<40' variants.vcf.gz -Oz -o filtered.vcf.gz
```

**GATK** (Genome Analysis Toolkit) provides the gold-standard HaplotypeCaller for more rigorous variant discovery. Its GVCF workflow — calling variants per sample, then jointly genotyping across populations — is essential for plant breeding panels where hundreds of lines are analyzed together. The critical plant-specific parameter is `--ploidy`: set to 2 for diploid species, 4 for tetraploid potato, 6 for hexaploid wheat, or 8 for octoploid strawberry. GATK's hard-filtering approach (filtering on QD, FS, MQ, SOR, MQRankSum, ReadPosRankSum) is recommended for plant genomes that lack curated variant training sets needed for machine-learning-based VQSR.

### Quality control and trimming

**FastQC** generates visual quality reports for raw FASTQ files, checking per-base quality scores, GC content distribution, adapter contamination, and duplication levels. **MultiQC** aggregates reports across all samples. For read trimming, **fastp** is the current best choice — it auto-detects adapters, trims low-quality bases, generates an HTML quality report, and runs substantially faster than the older Trimmomatic:

```bash
fastp -i reads_R1.fastq.gz -I reads_R2.fastq.gz \
  -o clean_R1.fastq.gz -O clean_R2.fastq.gz \
  --detect_adapter_for_pe --cut_front --cut_tail \
  --cut_window_size 4 --cut_mean_quality 20 \
  --length_required 36 --html fastp_report.html --thread 8
```

### RNA-seq quantification

**Kallisto** performs ultra-fast pseudoalignment for RNA-seq, quantifying transcript abundances without full read alignment. It indexes a transcriptome FASTA (downloaded from Phytozome or Ensembl Plants), then processes paired-end reads in minutes rather than hours. Output files include `abundance.tsv` with TPM and estimated counts per transcript, ready for downstream differential expression analysis with DESeq2 or sleuth.

### Annotation and association analysis

**SnpEff** annotates variants with predicted functional effects (synonymous, missense, stop-gained, splice site) using gene model databases. It ships with pre-built databases for Arabidopsis, rice, maize, tomato, and many other species, and custom databases can be built from any GFF3 annotation file. Its companion **SnpSift** filters annotated VCFs to extract high-impact variants.

**PLINK** (v1.9/2.0) handles genome-wide association analysis, PCA for population structure, kinship matrices, and LD calculations. The `--allow-extra-chr` flag is essential for plant genomes with non-human chromosome names. **TASSEL**, developed specifically for plant genetics by the Buckler Lab at Cornell, provides GLM/MLM GWAS, genomic selection support, LD analysis, and native GBS pipeline integration through both GUI and command-line interfaces.

### Key file formats at a glance

| Format | Purpose | Structure |
|--------|---------|-----------|
| **FASTQ** | Raw sequencing reads | 4-line records: header, sequence, separator, quality scores (Phred+33) |
| **BAM/SAM** | Aligned reads | 11 mandatory fields including position, mapping quality, CIGAR string |
| **VCF** | Genetic variants | Tab-delimited with genotype fields (0/0, 0/1, 1/1); polyploid: 0/0/0/1 |
| **GFF3** | Genome annotation | Hierarchical gene models (gene → mRNA → exon → CDS) |
| **BED** | Genomic intervals | 0-based coordinates; used for target regions and coverage analysis |

---

## 2. The molecular architecture of cold tolerance

Cold tolerance in plants is governed by a well-characterized signaling cascade centered on the **CBF/DREB1 pathway**, the master regulatory system for cold acclimation. Understanding these genes and their markers is foundational for any breeding program targeting northern climates.

### The CBF cold-response cascade

When temperatures drop to 0–4°C, membrane rigidification triggers calcium influx, which activates **ICE1** (Inducer of CBF Expression 1), a constitutively expressed bHLH transcription factor. ICE1 is post-translationally activated by sumoylation (via SIZ1) and binds MYC elements in the promoters of **CBF1/DREB1B**, **CBF2/DREB1C**, and **CBF3/DREB1A** — three tandemly arranged transcription factors on chromosome 4 in Arabidopsis. These CBFs are induced within **15 minutes** of cold exposure and activate hundreds of downstream **COR** (Cold-Regulated) genes by binding CRT/DRE cis-elements in their promoters.

The effector COR genes include **COR15a** (a chloroplast-targeted polypeptide that stabilizes membranes against hexagonal II phase lipid transitions during freezing), **COR47/RD17** (a dehydrin), and **COR78/RD29A** (encoding a hydrophilic cryoprotective protein). In wheat, **WCS120** — a 120 kDa dehydrin whose accumulation level directly correlates with LT50 (lethal temperature for 50% kill) — serves as both a functional gene and a molecular screening marker.

### Dehydrins and LEA proteins provide cellular protection

**Dehydrins** (Group II LEA proteins) are the primary cryoprotectants. Characterized by conserved K-segments (EKKGIMDKIKEKLPG), they stabilize membranes and proteins during the cellular dehydration caused by extracellular ice crystal formation. In barley, the dehydrin genes **Dhn1, Dhn3, Dhn5, Dhn7**, and **Dhn9** cluster near the Fr-H1 frost-resistance locus. In wheat, **WCOR410** associates directly with the plasma membrane lipid bilayer. In apple, **MdDHN** genes are linked to bud cold hardiness, and in peach, **PpDhn1** shows similar associations.

The broader **LEA protein family** (Groups I–VII) functions as molecular shields that prevent protein aggregation, stabilize enzymes, and sequester ions during dehydrative stress. **HVA1** (a Group III LEA from barley) has been widely used in transgenic cold-tolerance studies.

### Chromosomal architecture of frost resistance

In wheat, cold tolerance maps to two major locus groups on homoeologous group 5 chromosomes. **Fr-A1/Fr-B1/Fr-D1** co-localize with VRN1 vernalization genes, while **Fr-A2/Fr-B2/Fr-D2** co-localize with expanded CBF gene clusters. The Fr-A2 locus on chromosome 5A alone explains **20–40%** of frost tolerance variation and contains approximately 15 CBF genes whose copy number variation (CNV) is a functional marker — lines with extra copies of **TaCBF-A14** consistently show greater frost tolerance.

In barley, the parallel loci **Fr-H1** (co-localized with VRN-H1 on chromosome 5H, explaining ~30% of frost tolerance) and **Fr-H2** (co-localized with the HvCBF cluster, explaining ~20%) have been mapped using the extensively studied Nure × Tremois population. The individual genes **HvCBF2** and **HvCBF4** show the strongest associations with freezing survival.

For fruit trees, the genomic picture is more complex. In apple, QTLs for cold hardiness and bud dormancy map to linkage groups **LG1, LG3, LG7, LG9**, and **LG16**. The **MdDAM** (Dormancy-Associated MADS-box) genes regulate endodormancy entry and cold acclimation timing. In grape, cold-hardiness QTLs on chromosomes 15 and 2 have been identified using *V. riparia* and *V. amurensis* as cold-tolerant parents, with **VvCBF1–4** as candidate genes.

### Practical markers for breeding

KASP markers have been developed for **Fr-A2 CBF alleles** in wheat and are used operationally in breeding programs. SNP markers in **TaCBF-A14** and **TaCBF-A15** distinguish frost-tolerant from frost-sensitive genotypes. SSR markers **Xwmc48** and **Xbarc74** flank the Fr-A2 locus on 5A, while **Bmac0096**, **HVM3**, and **HVM20** tag Fr-H1 and Fr-H2 in barley. CBF copy number can be assayed by qPCR. For VRN1 allele discrimination (winter vs. spring habit), KASP genotyping is routine and indirectly selects for cold hardiness potential.

---

## 3. Nordic breeding programs and what has worked

Scandinavia's breeding programs have produced some of the world's most winter-hardy crop varieties by combining controlled freeze testing, ice-encasement screening, genomic tools, and germplasm from extreme environments.

### The major programs

**Graminor AS** (Ridabu, Norway) breeds winter and spring wheat, 6-row barley, oats, potatoes, and forage grasses for Norwegian conditions (USDA zones 3–5). Their winter wheat variety **'Magnifik'** combines winterhardiness with bread-making quality for southern Norway, while forage grass selections are screened specifically for persistence under ice encasement and *Microdochium nivale* snow mold. Graminor has invested in marker-assisted breeding and participates in collaborative genomic selection projects with NMBU and NIBIO.

**Boreal Plant Breeding** (Jokioinen, Finland) operates at the extreme end of agricultural cold tolerance, developing varieties for Finland's USDA zones 2–5 and growing seasons of just 90–130 days. Their winter wheat **'Veli'** and winter rye **'Elonkerjuu'** exhibit exceptional winterhardiness. Boreal has adopted Illumina SNP genotyping arrays and is implementing genomic selection in cereals in partnership with Luke (Natural Resources Institute Finland).

**SLU** (Swedish University of Agricultural Sciences) conducts both fundamental research and applied breeding, particularly in horticultural crops. Their Balsgård station produced Sweden's most popular apple, **'Aroma'** (Filippa × Ingrid Marie cross), along with 'Katja', 'Frida', and 'Kim'. SLU also researches haskap/honeyberry adaptation and cold hardiness physiology in woody plants. Commercial cereal breeding in Sweden now operates through **Lantmännen**, which produces winter wheat varieties like 'Julius', 'Stava', and 'Skagen'.

**NordGen** (Nordic Genetic Resource Center), headquartered in Alnarp, Sweden, maintains over **33,000 accessions** of cultivated plants across the Nordic countries and coordinates the Svalbard Global Seed Vault backup. Its Public-Private Partnership for Pre-Breeding (PPPB) screens historical cultivars and landraces for frost tolerance, ice encasement tolerance, and disease resistance alleles not present in modern germplasm.

### Crops and varieties that define Nordic success

Cold-hardy berry crops represent some of the most distinctive Nordic breeding achievements. **Haskap/honeyberry** (*Lonicera caerulea*) selections survive **-45°C** (zone 2), and varieties like 'Tundra', 'Borealis', and 'Aurora' from the University of Saskatchewan (bred from Japanese × Russian crosses) fruit before strawberry season thanks to flowers that tolerate -7°C frost. Finnish **sea buckthorn** varieties 'Tytti', 'Terhi', and 'Tarmo' were bred by Luke for reduced thorniness, larger berries, and high vitamin C content. **Lingonberry** cultivar 'Sussi' (Finland) and 'Koralle' (Germany) represent early domestication of a traditionally wild-harvested species. **Arctic bramble** varieties 'Mespi', 'Pima', and 'Marika' offer exceptional aromatic quality despite low yields.

For cold-hardy grapes, the University of Minnesota's interspecific hybrids have transformed northern viticulture. **'Marquette'** (zone 3, surviving -34°C) produces high-quality red wine from complex pedigrees including *V. riparia* and *V. vinifera*. The Latvian variety **'Zilga'** is extremely hardy (zone 3–4) and ripens in short Nordic growing seasons. Southern Sweden, Denmark, and southern Norway now grow 'Solaris', 'Rondo', 'Marquette', and 'Zilga' commercially.

### Techniques that distinguish Nordic breeding

Nordic programs employ several screening methods unique to their conditions. **Ice encasement tolerance testing** — subjecting plants to prolonged ice encasement simulating winter rain-thaw-refreeze cycles — addresses a major cause of winterkill distinct from simple freezing. **Controlled freeze testing** for LT50 determination uses programmable chambers ramping at -2°C per hour. **Snow mold inoculation** with *Microdochium nivale* under simulated snow cover is critical for forage grasses and winter cereals.

Multi-location testing across latitudinal gradients (e.g., 60°N to 67°N in Finland) captures genotype × environment interactions for winter survival. Drone-based and satellite **NDVI assessment** of winter survival across field trials provides rapid, large-scale phenotyping. **Electrical impedance spectroscopy** offers non-destructive cold hardiness estimation in woody plants, while **differential thermal analysis (DTA)** determines bud supercooling points.

Genomic approaches in Nordic programs include CBF gene copy number assays (qPCR-based), KASP marker panels for VRN1 and FR-A2 alleles, genomic selection models incorporating multi-year winter survival data, and speed breeding combined with genomic prediction to accelerate genetic gain.

---

## 4. Connecting genotype to phenotype

Three complementary statistical frameworks connect genetic variation to plant traits: QTL mapping in structured populations, GWAS in diversity panels, and genomic selection for predicting breeding value. Each serves a different purpose in the breeding pipeline.

### QTL mapping identifies trait-linked regions in crosses

QTL mapping exploits linkage disequilibrium in bi-parental or multi-parental populations. Two parents differing in a target trait are crossed, their progeny genotyped and phenotyped, and statistical tests identify genomic regions co-segregating with the trait. **Composite Interval Mapping (CIM)** — scanning marker intervals while controlling for genetic background using cofactors — is the standard method, typically requiring LOD scores ≥ 3 for significance.

Population types range from F2 populations (fast to develop, all genotype classes present) to **RILs** (recombinant inbred lines, homozygous and immortal after 6–8 generations of single-seed descent) to **MAGIC** populations (multi-parent advanced generation inter-crosses offering higher mapping resolution). Doubled haploid populations are particularly useful in Brassica, cucumber, and melon where the technology is well-established.

Key software includes **R/qtl** and its successor **R/qtl2** (supporting multi-parent populations and high-density markers), **IciMapping** (ICIM-ADD and ICIM-EPI models from CIMMYT), and **QTL Cartographer**. A typical workflow requires **150–300 individuals**, genotyped by SNP array or GBS, with a linkage map constructed using MSTmap or Lep-MAP3, followed by CIM with 1,000 permutations for threshold determination.

### GWAS achieves finer resolution in natural populations

Genome-wide association studies use diversity panels of 200–1,000+ accessions and historical recombination to map trait associations at higher resolution than QTL mapping. The critical challenge is population structure: related individuals share alleles that create spurious associations. The **MLM (Mixed Linear Model)** with population structure (Q matrix from PCA or ADMIXTURE) and kinship (K matrix, typically VanRaden method) corrections is the gold standard.

**FarmCPU** (Fixed and random model Circulating Probability Unification) represents the current best-practice algorithm, iterating between fixed-effect marker testing and random-effect pseudo-QTN selection to achieve high power with good false-positive control. **GAPIT3** (R package) implements FarmCPU, BLINK, MLM, and other models with publication-ready Manhattan and Q-Q plots. **GEMMA** provides exact MLM computation in C++ for very large datasets. **TASSEL** offers integrated GBS pipeline support.

Significance thresholds use Bonferroni correction (0.05/number of markers) or FDR (Benjamini-Hochberg). Candidate genes are identified within the LD decay distance of significant SNPs, then validated with expression data or independent populations.

### Genomic selection predicts value without phenotyping

Genomic selection uses genome-wide markers to predict breeding values of unphenotyped individuals — bypassing the need to identify specific QTLs and dramatically shortening breeding cycles. In perennial horticultural crops like apple, blueberry, and grape, where phenotypic evaluation takes 5–12 years, GS can reduce cycles to **3–4 years**.

**GBLUP** (Genomic BLUP) replaces the traditional pedigree-based relationship matrix with a genomic relationship matrix (G matrix, calculated using VanRaden's method). It assumes an infinitesimal architecture (many small-effect loci) and is computationally efficient. **Bayesian methods** (BayesA, BayesB, BayesCπ, BayesR) estimate marker-specific variances and outperform GBLUP when trait architecture includes few large-effect QTLs — as is the case for cold tolerance with its major Fr-2 locus.

Key R packages include **rrBLUP** (`mixed.solve()` for marker effects, `kin.blup()` for GBLUP), **BGLR** (comprehensive Bayesian methods), and **sommer** (multi-trait, multi-environment models). Training populations of **500–2,000 individuals** yield typical prediction accuracies of **r = 0.3–0.7** for complex horticultural traits. GS models incorporating CBF markers as fixed effects alongside genome-wide random markers show improved prediction accuracy for cold tolerance specifically.

### RNA-seq reveals the expression landscape behind traits

Differential expression analysis using **DESeq2** or **edgeR** (both R/Bioconductor packages) identifies genes whose expression changes between conditions — resistant vs. susceptible, cold-acclimated vs. control, ripe vs. unripe fruit. Both use negative binomial models for count data; DESeq2 tends to be more conservative and is better for smaller experiments (3–20 samples per group), while edgeR offers slightly more power with larger sample sizes.

**WGCNA** (Weighted Gene Co-expression Network Analysis) identifies modules of co-expressed genes and correlates module eigengenes with external traits, revealing entire gene networks underlying phenotypic variation. Hub genes within trait-associated modules become high-priority candidates. The workflow involves variance-stabilizing transformation, soft-thresholding power selection (target R² > 0.8 for scale-free topology), blockwise module construction, and module-trait correlation analysis. Results export to **Cytoscape** for network visualization.

### From discovery to breeding decisions

The path from identified markers to practical breeding runs through **KASP assays** (Kompetitive Allele-Specific PCR). Two allele-specific forward primers with different fluorescent tails compete for binding, producing a fluorescent signal that discriminates genotypes in 96 or 384-well plates at **~$1–5 per data point**. KASP markers exist for apple scab resistance (*Rvi6/Vf*), tomato TYLCV resistance (Ty-1/2/3), peach fruit quality loci, and numerous cereal disease and quality genes.

**Marker-assisted backcrossing (MABC)** operates at three levels: foreground selection (KASP markers for the target gene), background selection (genome-wide GBS or SNP array to maximize recurrent parent recovery), and recombinant selection (flanking markers to minimize linkage drag). With background selection, breeders can achieve >95% recurrent parent genome recovery by BC2, compared to the expected 93.75% at BC3 without molecular selection.

---

## 5. Building the physical infrastructure

### Greenhouse and environmental control

Breeding trial greenhouses require environmental control systems matched to the research goals. Entry-level climate automation from **Priva Connext** runs $5,000–$15,000, with full automation from Argus Controls or Wadsworth reaching $30,000–$100,000+. Supplemental LED lighting (**Fluence SPYDR 2x** at ~$800–$1,200 per fixture, or **Gavita Pro 1700e** at ~$900–$1,100) provides photoperiod control, while automated blackout curtains ($3,000–$10,000 per bay) enable short-day/long-day manipulation for photoperiod-sensitive species.

For cold-hardiness screening, programmable freezing chambers from **Tenney Environmental** or **Thermotron** ($15,000–$50,000) provide controlled freeze-thaw cycling. A practical DIY alternative uses modified chest freezers with **Inkbird ITC-308** external temperature controllers (~$35–$40), achieving controlled freezing to -20°C for approximately $300–$500 total. LT50 electrolyte leakage assays require only a conductivity meter (~$200–$500), sample tubes, and a boiling water bath.

Pollination isolation uses fine mesh cages (**BugDorm** at ~$50–$150 each), glassine pollination bags ($0.10–$0.50 each), and separate greenhouse bays with independent ventilation for pollen-contamination-critical crosses.

### Molecular biology lab essentials

DNA extraction using the **CTAB method** (Doyle & Doyle, 1987) requires a microcentrifuge (~$3,000–$4,500), 65°C heat block (~$300–$600), tissue homogenizer (**Qiagen TissueLyser II** at ~$5,000–$7,000, or mortar/pestle with liquid nitrogen for ~$350), fume hood for chloroform work, and a micropipette set (~$800–$1,500). Per-extraction reagent costs run $2–$5. Commercial kit alternatives like **Qiagen DNeasy Plant Mini Kit** ($5–$8/sample) trade higher per-sample cost for faster processing.

The **Oxford Nanopore MinION** provides in-house sequencing capability at accessible price points. The MinION starter pack costs ~$1,000, with R10.4.1 flow cells at ~$900 each (15–30 Gb output) or Flongle flow cells at ~$90 each (1–2 Gb output). Library prep kits (Ligation Sequencing SQK-LSK114 at ~$600 for 6 reactions, or Rapid Sequencing SQK-RAD114 for 10-minute prep) bring per-run costs to $1,000–$1,500 for a full flow cell or $100–$200 for Flongle runs. MinION excels at amplicon sequencing for marker validation, structural variant detection, and pathogen identification in breeding nurseries.

### Trial design and data management

Experimental designs for breeding trials include **RCBD** (randomized complete block design) as the standard, **augmented designs** (replicated checks + unreplicated entries, ideal for early-generation trials with limited seed; supported by the `augmentedRCBD` R package), and **alpha-lattice designs** for trials exceeding 20 entries (generated using DiGGer or CycDesigN). Spatial analysis with **SpATS** or **ASReml-R** further improves precision by modeling environmental gradients across greenhouse benches.

The **Breeding Management System (BMS)** from the Integrated Breeding Platform provides free, open-source germplasm management, crossing records, nursery management, and trial design. The **Field Book App** (Android, free) enables tablet-based phenotypic data collection with barcode scanning, custom traits, and GPS tagging. Both connect through the **BrAPI** (Breeding API v2.1) standard, enabling seamless data flow from field collection through database to R-based analysis. **Breedbase** (from Boyce Thompson Institute) offers a complementary web-based platform with genomic selection, trial management, and crossing plan functionality.

### Open-source environmental monitoring

A complete greenhouse monitoring station costs under $200 using a **Raspberry Pi 4** (~$55–$75) with **BME280** sensors (temperature + humidity + pressure, ~$10), **BH1750** light sensors (~$5), **DS18B20** waterproof soil temperature probes (~$3–$5 each), capacitive soil moisture sensors (~$5–$8 each), and an **MH-Z19B** CO2 sensor (~$25). Data flows through **MQTT** (Mosquitto broker) to **InfluxDB** (time-series database) and **Grafana** (visualization dashboards), all running free and open-source on the Pi itself. Alert rules in Grafana trigger email or SMS notifications when environmental parameters drift out of range.

For distributed monitoring across multiple greenhouse bays, **ESP32** microcontrollers (~$5–$15 each, with built-in WiFi) serve as wireless sensor nodes reporting to a central Raspberry Pi hub. The architecture — sensors → ESP32 nodes → WiFi/MQTT → Raspberry Pi → InfluxDB + Grafana — scales from a single hobby greenhouse to multi-bay research facilities.

---

## 6. Where to find plant genomic data

Open-source databases provide the reference genomes, gene annotations, variant catalogs, and expression data that underpin all genomic breeding work.

**Phytozome** (phytozome-next.jgi.doe.gov) hosts genome assemblies and GFF3 annotations for **250+** plant species, with bulk downloads of genome FASTA, CDS, and protein sequences. Run by DOE-JGI, it is the primary resource for soybean, poplar, sorghum, Medicago, and many other crop and model species. **Ensembl Plants** (plants.ensembl.org) provides genome browsers, BioMart query tools, variation data, and comparative genomics for 60+ plant species, with programmatic REST API access and FTP downloads of VCF, GFF3, and FASTA files. **Gramene** (gramene.org) complements these with curated Plant Reactome pathways, QTL data, synteny maps, and gene trees for 90+ species, maintained by Cold Spring Harbor Laboratory and USDA.

The **1001 Genomes Project** (1001genomes.org) provides whole-genome sequences for **1,135+ natural Arabidopsis accessions** with downloadable VCF files containing millions of SNPs — a foundational GWAS resource. **TAIR** (arabidopsis.org) remains the gold-standard Arabidopsis annotation (TAIR10/Araport11) with gene functional descriptions, GO annotations, and metabolic pathways. Crop-specific databases include **MaizeGDB** (maizegdb.org), **GrainGenes** (wheat.pw.usda.gov) for wheat/barley/oats/rye, and the **Sol Genomics Network** (solgenomics.net) for Solanaceae.

Raw sequencing data from any published plant study can be retrieved from the **NCBI Sequence Read Archive** using `prefetch` and `fasterq-dump` from the SRA Toolkit, or more often via faster direct FASTQ downloads from **EBI ENA** (ebi.ac.uk/ena).

---

## 7. Scaling from 10 plants to 10,000

### Small scale ($500–$5,000): establishing proof of concept

A minimal viable breeding operation starts with a hobby greenhouse ($300–$800), basic environmental monitoring (Govee WiFi sensors, ~$30), hand pollination tools, and the free Field Book app for data recording. Genotyping at this scale means outsourcing **KASP assays** to service labs like Intertek/AgriPlex at $2–$5 per data point, targeting known QTL markers for the traits of interest. Pedigree tracking lives in spreadsheets or the free BMS platform. This setup supports 10–50 plants per generation with targeted marker screening for 1–3 loci.

### Medium scale ($10,000–$100,000): implementing molecular breeding

Scaling to 100–1,000 plants per generation introduces in-house KASP genotyping (requiring a fluorescent plate reader like BioTek Synergy, $5,000–$15,000 used), 96-well DNA extraction with Qiagen DNeasy 96 kits, and a PCR thermal cycler (~$3,000–$4,500). Genotyping-by-sequencing through **DArTseq** ($15–$30/sample for thousands of markers) or Cornell GBS protocol enables genome-wide marker coverage. A MinION starter pack provides flexible in-house sequencing for marker validation. Commercial greenhouse structures ($5,000–$15,000) with automated irrigation and climate control support replicated trial designs. BMS or Breedbase manages crossing plans and trial data through BrAPI-connected workflows.

### Large scale ($100,000+): full genomic breeding pipeline

At 1,000+ plants, high-throughput genotyping platforms become essential: Illumina Infinium or Axiom SNP arrays ($50–$150/sample), GBS at scale ($15–$25/sample), or emerging skim-seq approaches ($10–$20/sample). Automated phenotyping via drone-based multispectral imaging (DJI Matrice + MicaSense RedEdge-P, ~$15,000 total) or conveyor-based greenhouse imaging systems (LemnaTec, $200K–$1M+) generates the high-quality phenotypic data that genomic selection models demand. **GBLUP** and Bayesian prediction models in rrBLUP and BGLR produce genomic estimated breeding values for ranking and selection of unphenotyped seedlings.

### Computational infrastructure that scales with the program

Bioinformatics pipelines should be built with **Nextflow** or **Snakemake** workflow managers from the start, using **Docker** containers (or **Singularity/Apptainer** on HPC clusters) for reproducibility. The nf-core community provides pre-built, validated pipelines for variant calling (nf-core/sarek), RNA-seq (nf-core/rnaseq), and other common workflows. **Galaxy** (usegalaxy.org) offers a web-based GUI alternative for teams with mixed computational skills.

Storage requirements grow rapidly: a single whole-genome sequencing run for 100 plant samples generates 1–5 TB of raw data. Cloud computing via **AWS** (EC2 Spot Instances for 60–90% cost reduction, S3 for storage at ~$0.02/GB/month) or **Google Cloud** (Preemptible VMs) provides elastic scaling for burst computation. A typical variant calling pipeline for 100 samples costs $50–$200 on cloud infrastructure. For predictable, regular workloads, university HPC clusters (often free or subsidized for academics) remain more cost-effective.

Version control with **Git** ensures analysis reproducibility, while a PostgreSQL-backed, BrAPI-compliant database infrastructure connects wet-lab sample tracking (LIMS) through genotyping pipelines to breeding decision support tools.

---

## Conclusion

The technical barriers to genomics-assisted plant breeding have collapsed. The entire software stack — from read alignment through variant calling to genomic prediction — is open-source and installable with a single `conda` command. The biological knowledge connecting CBF gene copy number variation to frost tolerance, or DAM genes to dormancy timing, is mature enough to drive practical marker-assisted selection decisions today. Nordic breeding programs at Graminor, Boreal, and SLU have demonstrated that combining controlled-environment phenotyping (ice encasement screening, programmable freeze testing) with genomic selection models yields varieties like 'Veli' wheat and 'Marquette' grape that push agriculture's northern frontier.

The most actionable insight for a new program is that **scaling is not primarily a technology problem but an integration problem**. A breeder with a $2,000 budget can run KASP markers on CBF alleles and make informed selection decisions. The challenge at every scale is connecting data flows — from barcode-scanned phenotype records in Field Book, through BrAPI-compliant databases, to R-based genomic prediction models, and back to crossing decisions. Programs that invest in this data architecture early, even at small scale, avoid the painful retrofitting that stalls many operations trying to scale from artisanal to systematic breeding. The tools exist. The genomes are sequenced. The path from sequence to selection is now a workflow engineering problem, not a scientific one.

---

*VÄXT · Heritage grain breeding & open-source seed commons · CC BY 4.0 · You may share and adapt with attribution.*